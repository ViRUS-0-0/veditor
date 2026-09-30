"""Trims a media file to scheduled start and end bounds.

Attempts fast, lossless stream-copy remuxing by default. Falls back to full
decode and re-encode if stream copy fails or is incompatible with the output container.
"""

from __future__ import annotations

import logging
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any

import av

from app.pipeline.loudness import _mux_packet_with_monotonic_dts, rescale_pts

logger = logging.getLogger(__name__)


class CutStrategy(str, Enum):
    STREAM_COPY = "stream_copy"
    RE_ENCODE = "re_encode"
    SMART_CUT = "smart_cut"


DECODER_TO_ENCODER_VIDEO: dict[str, str] = {
    "h264": "libx264",
    "hevc": "libx265",
    "h265": "libx265",
    "vp8": "libvpx",
    "vp9": "libvpx-vp9",
    "av1": "libsvtav1",
    "mpeg4": "mpeg4",
}

DECODER_TO_ENCODER_AUDIO: dict[str, str] = {
    "aac": "aac",
    "mp3": "libmp3lame",
    "opus": "libopus",
    "vorbis": "libvorbis",
    "flac": "flac",
    "pcm_s16le": "pcm_s16le",
}


def _resolve_video_encoder(decoder_name: str | None) -> str:
    """Map a decoder codec name (e.g., 'h264') to an encoder (e.g., 'libx264')."""
    if not decoder_name:
        return "libx264"
    return DECODER_TO_ENCODER_VIDEO.get(decoder_name.lower(), "libx264")


def _resolve_audio_encoder(decoder_name: str | None) -> str:
    """Map an audio decoder codec name to an encoder."""
    if not decoder_name:
        return "aac"
    return DECODER_TO_ENCODER_AUDIO.get(decoder_name.lower(), "aac")


def cut(
    input_path: Path | str,
    output_path: Path | str,
    start_seconds: float,
    end_seconds: float,
    *,
    force_reencode: bool = False,
    threads: int | None = None,
) -> CutStrategy:
    """Trim an input recording to the [start_seconds, end_seconds] window.

    Args:
        input_path: Path to the raw source recording.
        output_path: Destination path for the trimmed output.
        start_seconds: Start timestamp in seconds (non-negative).
        end_seconds: End timestamp in seconds (greater than start_seconds).
        force_reencode: If True, bypass stream-copy and perform full re-encode.
        threads: Optional thread limit for video re-encoding fallback.

    Returns:
        CutStrategy: CutStrategy.STREAM_COPY, CutStrategy.RE_ENCODE, or CutStrategy.SMART_CUT.

    Raises:
        ValueError: If timestamps or input paths are invalid.
        FileNotFoundError: If input_path does not exist.
    """
    in_path = Path(input_path)
    out_path = Path(output_path)

    if not in_path.is_file():
        raise FileNotFoundError(f"Input file not found: {in_path}")

    if in_path.resolve() == out_path.resolve():
        raise ValueError(
            f"Input and output paths must be different to prevent file truncation: {in_path}"
        )

    if start_seconds < 0:
        raise ValueError(f"start_seconds must be non-negative: {start_seconds}")

    if end_seconds <= start_seconds:
        raise ValueError(
            f"end_seconds ({end_seconds}) must be greater than start_seconds ({start_seconds})"
        )

    if threads is not None and threads <= 0:
        raise ValueError(f"threads must be greater than zero: {threads}")

    # storage-boundary-exempt: creating parent directory for pipeline output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not force_reencode:
        try:
            return _cut_smart(
                str(in_path), str(out_path), start_seconds, end_seconds, threads=threads
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Smart cut failed (%s); falling back to full re-encode.",
                exc,
            )

    return _cut_reencode(
        str(in_path), str(out_path), start_seconds, end_seconds, threads=threads
    )


def _cut_smart(
    input_path: str,
    output_path: str,
    start_seconds: float,
    end_seconds: float,
    threads: int | None = None,
) -> CutStrategy:
    """Frame-accurate smart / hybrid cut with stream copy of interior GOPs."""
    with av.open(input_path) as in_container:
        video_streams = list(in_container.streams.video)
        audio_streams = list(in_container.streams.audio)

        if not video_streams and not audio_streams:
            raise ValueError(f"No audio or video streams found in {input_path}")

        # If no video stream (e.g. audio-only), fallback to stream copy
        if not video_streams:
            return _cut_stream_copy(input_path, output_path, start_seconds, end_seconds)

        in_v = video_streams[0]
        in_a = audio_streams[0] if audio_streams else None

        fps_val = float(in_v.average_rate or in_v.guessed_rate or 24)
        fps = round(fps_val) if fps_val > 0 else 24
        epsilon = 0.5 / fps

        # Collect keyframe timestamps
        keyframes: list[float] = []
        for packet in in_container.demux(in_v):
            if packet.is_keyframe and packet.pts is not None:
                ts = float(packet.pts * in_v.time_base)
                keyframes.append(ts)
                if ts > end_seconds + 5.0:
                    break

        if not keyframes:
            keyframes = [0.0]

        pre_candidates = [k for k in keyframes if k <= start_seconds + epsilon]
        K_pre = max(pre_candidates) if pre_candidates else 0.0

        is_start_on_keyframe = abs(start_seconds - K_pre) <= epsilon

        video_duration = (
            float(in_v.duration * in_v.time_base)
            if in_v.duration
            else (
                float(in_container.duration / av.time_base)
                if in_container.duration
                else None
            )
        )

        nearest_k_end = (
            min((abs(end_seconds - k), k) for k in keyframes)[1] if keyframes else None
        )
        is_end_on_keyframe = (
            nearest_k_end is not None and abs(end_seconds - nearest_k_end) <= epsilon
        ) or (video_duration is not None and end_seconds >= video_duration - epsilon)

        # Exact keyframe bounds allow pure stream-copy
        if is_start_on_keyframe and is_end_on_keyframe:
            return _cut_stream_copy(input_path, output_path, start_seconds, end_seconds)

        if is_start_on_keyframe:
            K_start_body = K_pre
        else:
            next_candidates = [k for k in keyframes if k > start_seconds + epsilon]
            K_next = min(next_candidates) if next_candidates else None
            if K_next is None or K_next >= end_seconds:
                return _cut_reencode(
                    input_path, output_path, start_seconds, end_seconds, threads=threads
                )
            K_start_body = K_next

        # Last keyframe before or at end
        last_candidates = [k for k in keyframes if k <= end_seconds + epsilon]
        K_last = max(last_candidates) if last_candidates else None

        if is_end_on_keyframe:
            K_end_body = end_seconds
        else:
            if K_last is None or K_last <= K_start_body:
                return _cut_reencode(
                    input_path, output_path, start_seconds, end_seconds, threads=threads
                )
            K_end_body = K_last

    # Head: decode from K_pre, re-encode frames in [start_seconds, K_start_body)
    head_frames: list[av.VideoFrame] = []
    if not is_start_on_keyframe:
        with av.open(input_path) as container:
            v = container.streams.video[0]
            container.seek(int(K_pre * av.time_base), backward=True, any_frame=False)
            for pkt in container.demux(v):
                try:
                    decoded_frames = pkt.decode()
                except (av.error.InvalidDataError, av.FFmpegError) as exc:
                    logger.warning("Skipping unparseable head packet in cut: %s", exc)
                    continue
                for frame in decoded_frames:
                    t = (
                        float(frame.pts * v.time_base)
                        if frame.pts is not None
                        else (float(frame.time) if frame.time is not None else 0.0)
                    )
                    if t >= K_start_body - epsilon:
                        break
                    if t >= start_seconds - epsilon:
                        head_frames.append(frame)
                if head_frames and t >= K_start_body - epsilon:
                    break

    # Tail: decode from K_end_body, re-encode frames in [K_end_body, end_seconds]
    tail_frames: list[av.VideoFrame] = []
    if not is_end_on_keyframe:
        with av.open(input_path) as container:
            v = container.streams.video[0]
            container.seek(
                int(K_end_body * av.time_base), backward=True, any_frame=False
            )
            for pkt in container.demux(v):
                try:
                    decoded_frames = pkt.decode()
                except (av.error.InvalidDataError, av.FFmpegError) as exc:
                    logger.warning("Skipping unparseable tail packet in cut: %s", exc)
                    continue
                for frame in decoded_frames:
                    t = (
                        float(frame.pts * v.time_base)
                        if frame.pts is not None
                        else (float(frame.time) if frame.time is not None else 0.0)
                    )
                    if t > end_seconds + epsilon:
                        break
                    if t >= K_end_body - epsilon:
                        tail_frames.append(frame)
                if tail_frames and t > end_seconds + epsilon:
                    break

    container_options = (
        {"movflags": "faststart"}
        if output_path.lower().endswith((".mp4", ".mov", ".m4v"))
        else {}
    )
    with (
        av.open(input_path) as in_container,
        av.open(output_path, mode="w", options=container_options) as out_container,
    ):
        in_v = in_container.streams.video[0]
        in_a = in_container.streams.audio[0] if in_container.streams.audio else None
        out_v = out_container.add_stream_from_template(in_v)
        out_a = None
        if in_a:
            try:
                out_a = out_container.add_stream_from_template(in_a)
            except ValueError, av.FFmpegError:
                sample_rate = in_a.codec_context.sample_rate or 44100
                channels = in_a.codec_context.channels or 1
                out_a = out_container.add_stream("aac", rate=sample_rate)
                if in_a.codec_context.layout:
                    out_a.layout = in_a.codec_context.layout.name
                elif channels == 2:
                    out_a.layout = "stereo"
                else:
                    out_a.layout = "mono"

        last_dts: dict[int, int] = {}

        # 1. Stream-copy audio packets from start_seconds to end_seconds
        if in_a and out_a:
            in_container.seek(
                int(start_seconds * av.time_base),
                backward=True,
                any_frame=False,
            )
            first_a_pts = None
            for p in in_container.demux(in_a):
                if p.pts is None:
                    continue
                t = float(p.pts * in_a.time_base)
                if t > end_seconds:
                    break
                if t >= start_seconds:
                    if first_a_pts is None:
                        first_a_pts = p.pts
                    p.pts -= first_a_pts
                    if p.dts is not None:
                        p.dts -= first_a_pts
                    rescale_pts(p, in_a.time_base, out_a.time_base)
                    p.stream = out_a
                    _mux_packet_with_monotonic_dts(
                        out_container, p, out_a.index, last_dts
                    )

        pts_per_frame = round(Fraction(1, fps) / out_v.time_base)

        # 2. Encode & Mux Video Head [start_seconds, K_start_body)
        if head_frames:
            head_options = {"preset": "ultrafast"}
            if threads is not None:
                head_options["threads"] = str(threads)
            encoder_name = _resolve_video_encoder(in_v.codec_context.name)
            head_ctx = av.CodecContext.create(av.Codec(encoder_name, "w"))
            head_ctx.width = in_v.codec_context.width
            head_ctx.height = in_v.codec_context.height
            head_ctx.pix_fmt = in_v.codec_context.pix_fmt or "yuv420p"
            head_ctx.time_base = Fraction(1, fps)
            head_ctx.framerate = Fraction(fps, 1)
            head_ctx.options = head_options
            head_ctx.open()

            for i, h_frame in enumerate(head_frames):
                if h_frame.format.name != head_ctx.pix_fmt:
                    h_frame = h_frame.reformat(format=head_ctx.pix_fmt)
                h_frame.pts = i
                h_frame.time_base = head_ctx.time_base
                for p in head_ctx.encode(h_frame):
                    rescale_pts(p, head_ctx.time_base, out_v.time_base)
                    p.stream = out_v
                    _mux_packet_with_monotonic_dts(
                        out_container, p, out_v.index, last_dts
                    )
            for p in head_ctx.encode():
                rescale_pts(p, head_ctx.time_base, out_v.time_base)
                p.stream = out_v
                _mux_packet_with_monotonic_dts(out_container, p, out_v.index, last_dts)

        body_start_pts = len(head_frames) * pts_per_frame
        max_body_pts = body_start_pts

        # 3. Stream-copy Video Body [K_start_body, K_end_body) with Annex B bitstream filter
        bsf = None
        if (
            in_v.codec_context.name == "h264"
            and "h264_mp4toannexb" in av.bitstream_filters_available
        ):
            bsf = av.BitStreamFilterContext("h264_mp4toannexb", in_stream=in_v)
        elif (
            in_v.codec_context.name in ("hevc", "h265")
            and "hevc_mp4toannexb" in av.bitstream_filters_available
        ):
            bsf = av.BitStreamFilterContext("hevc_mp4toannexb", in_stream=in_v)

        in_container.seek(
            int(K_start_body * av.time_base), backward=True, any_frame=False
        )
        body_first_dts = None
        body_first_pts = None
        for p in in_container.demux(in_v):
            if p.pts is None:
                continue
            t = float(p.pts * in_v.time_base)
            if t >= K_end_body - epsilon:
                break
            if t >= K_start_body - epsilon:
                if body_first_dts is None:
                    body_first_dts = p.dts if p.dts is not None else p.pts
                    body_first_pts = p.pts
                p.pts = p.pts - body_first_pts
                p.dts = (p.dts if p.dts is not None else p.pts) - body_first_dts
                rescale_pts(p, in_v.time_base, out_v.time_base)
                p.pts += body_start_pts
                p.dts += body_start_pts
                dur = p.duration if p.duration else pts_per_frame
                max_body_pts = max(max_body_pts, p.pts + dur)
                if bsf is not None:
                    for fp in bsf.filter(p):
                        fp.stream = out_v
                        _mux_packet_with_monotonic_dts(
                            out_container, fp, out_v.index, last_dts
                        )
                else:
                    p.stream = out_v
                    _mux_packet_with_monotonic_dts(
                        out_container, p, out_v.index, last_dts
                    )
        if bsf is not None:
            for fp in bsf.filter(None):
                fp.stream = out_v
                _mux_packet_with_monotonic_dts(out_container, fp, out_v.index, last_dts)

        tail_start_pts = max(body_start_pts, max_body_pts)

        # 4. Encode & Mux Video Tail [K_end_body, end_seconds]
        if tail_frames:
            tail_options = {"preset": "ultrafast"}
            if threads is not None:
                tail_options["threads"] = str(threads)
            encoder_name = _resolve_video_encoder(in_v.codec_context.name)
            tail_ctx = av.CodecContext.create(av.Codec(encoder_name, "w"))
            tail_ctx.width = in_v.codec_context.width
            tail_ctx.height = in_v.codec_context.height
            tail_ctx.pix_fmt = in_v.codec_context.pix_fmt or "yuv420p"
            tail_ctx.time_base = Fraction(1, fps)
            tail_ctx.framerate = Fraction(fps, 1)
            tail_ctx.options = tail_options
            tail_ctx.open()

            for j, t_frame in enumerate(tail_frames):
                if t_frame.format.name != tail_ctx.pix_fmt:
                    t_frame = t_frame.reformat(format=tail_ctx.pix_fmt)
                t_frame.pts = j
                t_frame.time_base = tail_ctx.time_base
                for p in tail_ctx.encode(t_frame):
                    rescale_pts(p, tail_ctx.time_base, out_v.time_base)
                    p.pts += tail_start_pts
                    if p.dts is not None:
                        p.dts += tail_start_pts
                    p.stream = out_v
                    _mux_packet_with_monotonic_dts(
                        out_container, p, out_v.index, last_dts
                    )
            for p in tail_ctx.encode():
                rescale_pts(p, tail_ctx.time_base, out_v.time_base)
                p.pts += tail_start_pts
                if p.dts is not None:
                    p.dts += tail_start_pts
                p.stream = out_v
                _mux_packet_with_monotonic_dts(out_container, p, out_v.index, last_dts)

    return CutStrategy.SMART_CUT


def _cut_stream_copy(
    input_path: str,
    output_path: str,
    start_seconds: float,
    end_seconds: float,
) -> CutStrategy:
    """Fast stream-copy remuxing without decoding."""
    with av.open(input_path) as in_container:
        streams = [*in_container.streams.video, *in_container.streams.audio]
        if not streams:
            raise ValueError(f"No audio or video streams found in {input_path}")

        # Seek container to the nearest keyframe at or before start_seconds
        seek_target = int(start_seconds * av.time_base)
        in_container.seek(seek_target, backward=True, any_frame=False)

        with av.open(output_path, mode="w") as out_container:
            out_streams: dict[int, av.stream.Stream] = {}
            offset_map: dict[int, int] = {}
            streams_past_end: set[int] = set()

            for stream in streams:
                out_stream = out_container.add_stream_from_template(stream)
                out_streams[stream.index] = out_stream

            for packet in in_container.demux(*streams):
                if packet.dts is None:
                    continue

                stream = packet.stream
                time_base = (
                    float(stream.time_base)
                    if stream.time_base is not None
                    else (1.0 / av.time_base)
                )
                packet_time_s = (
                    float(packet.pts * time_base)
                    if packet.pts is not None
                    else float(packet.dts * time_base)
                )

                if packet_time_s > end_seconds:
                    streams_past_end.add(stream.index)
                    if len(streams_past_end) >= len(streams):
                        break
                    continue

                if not in_container.streams.video and packet_time_s < start_seconds:
                    continue

                if stream.index not in offset_map:
                    offset_map[stream.index] = packet.dts

                base_offset = offset_map[stream.index]
                packet.stream = out_streams[stream.index]
                if packet.pts is not None:
                    packet.pts -= base_offset
                packet.dts -= base_offset

                out_container.mux(packet)

    return CutStrategy.STREAM_COPY


def _add_video_stream(
    container: av.container.OutputContainer,
    preferred_encoder: str,
    rate: Any,
    options: dict[str, str] | None = None,
) -> av.stream.Stream:
    """Add a video stream with preferred encoder, falling back to libx264 if incompatible."""
    try:
        return container.add_stream(preferred_encoder, rate=rate, options=options)
    except (ValueError, av.FFmpegError) as exc:
        logger.warning(
            "Video encoder '%s' not supported by container (%s); falling back to 'libx264'.",
            preferred_encoder,
            exc,
        )
        fallback_options = dict(options) if options else {}
        fallback_options.setdefault("preset", "veryfast")
        return container.add_stream("libx264", rate=rate, options=fallback_options)


def _add_audio_stream(
    container: av.container.OutputContainer,
    preferred_encoder: str,
    rate: int,
) -> av.stream.Stream:
    """Add an audio stream with preferred encoder, falling back to aac if incompatible."""
    try:
        return container.add_stream(preferred_encoder, rate=rate)
    except (ValueError, av.FFmpegError) as exc:
        logger.warning(
            "Audio encoder '%s' not supported by container (%s); falling back to 'aac'.",
            preferred_encoder,
            exc,
        )
        return container.add_stream("aac", rate=rate)


def _cut_reencode(
    input_path: str,
    output_path: str,
    start_seconds: float,
    end_seconds: float,
    threads: int | None = None,
) -> CutStrategy:
    """Full frame decode and re-encode fallback."""
    with av.open(input_path) as in_container:
        video_streams = list(in_container.streams.video)
        audio_streams = list(in_container.streams.audio)

        if not video_streams and not audio_streams:
            raise ValueError(f"No audio or video streams found in {input_path}")

        # Seek to start
        seek_target = int(start_seconds * av.time_base)
        in_container.seek(seek_target, backward=True, any_frame=False)

        with av.open(output_path, mode="w") as out_container:
            out_video = None
            out_audio = None
            video_time_base = Fraction(1, 24)
            sample_rate = 44100

            if video_streams:
                in_v = video_streams[0]
                encoder_name = _resolve_video_encoder(in_v.codec_context.name)
                fps = in_v.average_rate or in_v.guessed_rate or 24
                video_options: dict[str, str] = {}
                if encoder_name == "libx264":
                    video_options["preset"] = "ultrafast"
                if threads is not None:
                    video_options["threads"] = str(threads)
                out_video = _add_video_stream(
                    out_container,
                    encoder_name,
                    rate=fps,
                    options=video_options or None,
                )
                out_video.width = in_v.codec_context.width
                out_video.height = in_v.codec_context.height
                out_video.pix_fmt = in_v.codec_context.pix_fmt or "yuv420p"
                video_time_base = (
                    Fraction(1, 1) / Fraction(fps) if fps else Fraction(1, 24)
                )

            if audio_streams:
                in_a = audio_streams[0]
                encoder_name = _resolve_audio_encoder(in_a.codec_context.name)
                sample_rate = in_a.codec_context.sample_rate or 44100
                channels = in_a.codec_context.channels or 1
                out_audio = _add_audio_stream(
                    out_container, encoder_name, rate=sample_rate
                )
                if in_a.codec_context.layout:
                    out_audio.layout = in_a.codec_context.layout.name
                elif channels == 2:
                    out_audio.layout = "stereo"
                else:
                    out_audio.layout = "mono"

            streams_to_demux = [
                s for s in (video_streams[:1] + audio_streams[:1]) if s is not None
            ]

            video_frame_count = 0
            audio_sample_count = 0
            streams_past_end: set[int] = set()

            for packet in in_container.demux(*streams_to_demux):
                if len(streams_past_end) >= len(streams_to_demux):
                    break

                try:
                    decoded_frames = packet.decode()
                except (av.error.InvalidDataError, av.FFmpegError) as exc:
                    logger.warning(
                        "Skipping unparseable packet in cut reencode: %s", exc
                    )
                    continue
                for frame in decoded_frames:
                    time_base = (
                        float(frame.time_base) if frame.time_base is not None else 1.0
                    )
                    frame_time_s = (
                        float(frame.pts * time_base)
                        if frame.pts is not None
                        else (frame.time if frame.time is not None else 0.0)
                    )

                    if frame_time_s > end_seconds:
                        streams_past_end.add(packet.stream.index)
                        if len(streams_past_end) >= len(streams_to_demux):
                            break
                        continue

                    if frame_time_s < start_seconds:
                        continue

                    if isinstance(frame, av.VideoFrame) and out_video is not None:
                        if frame.format.name != out_video.pix_fmt:
                            try:
                                frame = frame.reformat(format=out_video.pix_fmt)
                            except (av.FFmpegError, ValueError) as exc:
                                logger.warning(
                                    "Frame reformat failed (%s), proceeding without reformat.",
                                    exc,
                                )
                        frame.pts = video_frame_count
                        frame.time_base = video_time_base
                        video_frame_count += 1
                        for enc_packet in out_video.encode(frame):
                            out_container.mux(enc_packet)

                    elif isinstance(frame, av.AudioFrame) and out_audio is not None:
                        frame.pts = audio_sample_count
                        frame.time_base = Fraction(1, sample_rate)
                        audio_sample_count += frame.samples
                        for enc_packet in out_audio.encode(frame):
                            out_container.mux(enc_packet)

            # Flush encoders
            if out_video is not None:
                for enc_packet in out_video.encode():
                    out_container.mux(enc_packet)
            if out_audio is not None:
                for enc_packet in out_audio.encode():
                    out_container.mux(enc_packet)

    return CutStrategy.RE_ENCODE
