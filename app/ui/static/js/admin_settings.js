document.addEventListener("DOMContentLoaded", () => {
  // ── 1. Tolerance Stepped Slider & Preset Definitions ──
  const PRESET_VALUES = [60, 180, 300, 600, 900, 1800];
  const toleranceSlider = document.getElementById("slider-detect_duration_tolerance_seconds");
  const hiddenInput = document.getElementById("input-detect_duration_tolerance_seconds");
  const toleranceReadout = document.getElementById("readout-detect_duration_tolerance_seconds");
  const toleranceBadge = document.getElementById("badge-detect_duration_tolerance_seconds");
  const presetPills = document.querySelectorAll(".preset-pill");
  const tickLabels = document.querySelectorAll(".tick-label");

  function formatTolerance(seconds) {
    const sec = parseInt(seconds, 10);
    const mins = Math.floor(sec / 60);
    const remSec = sec % 60;
    let label = `${mins} min${mins !== 1 ? "s" : ""}`;
    if (remSec > 0) {
      label += ` ${remSec}s`;
    }
    if (sec === 300) {
      label += " (Default)";
    } else if (sec <= 60) {
      label += " (Strict)";
    } else if (sec >= 1800) {
      label += " (Max)";
    }
    return label;
  }

  function syncToleranceByIndex(index) {
    const clampedIndex = Math.max(0, Math.min(PRESET_VALUES.length - 1, index));
    const seconds = PRESET_VALUES[clampedIndex];
    const pct = (clampedIndex / (PRESET_VALUES.length - 1)) * 100;

    if (toleranceSlider) {
      toleranceSlider.value = clampedIndex;
      toleranceSlider.style.setProperty("--range-pct", `${pct}%`);
    }

    if (hiddenInput) {
      hiddenInput.value = seconds.toFixed(1);
    }

    if (toleranceReadout) {
      toleranceReadout.textContent = formatTolerance(seconds);
    }

    if (toleranceBadge) {
      if (seconds === 300) {
        toleranceBadge.className = "setting-badge badge-default";
        toleranceBadge.textContent = "System Default";
      } else {
        toleranceBadge.className = "setting-badge badge-custom";
        toleranceBadge.textContent = "Custom Override";
      }
    }

    // Update active pill and tick label
    [...presetPills, ...tickLabels].forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.index) === clampedIndex);
    });
  }

  if (toleranceSlider) {
    const initialIdx = parseInt(toleranceSlider.value, 10);
    syncToleranceByIndex(Number.isInteger(initialIdx) ? initialIdx : 2);

    toleranceSlider.addEventListener("input", (e) => {
      syncToleranceByIndex(parseInt(e.target.value, 10));
    });
  }

  // ── 2. Preset Pill & Tick Click Handlers ──
  [...presetPills, ...tickLabels].forEach((el) => {
    el.addEventListener("click", () => {
      syncToleranceByIndex(parseInt(el.dataset.index, 10));
    });
  });

  // ── 3. Dropdown Live Sync with Badges ──
  const defaults = {
    loudness_target_lufs: "-16.0",
    default_preview_preset: "small_video",
    default_transcode_preset: "1080p_default",
  };

  Object.entries(defaults).forEach(([key, defaultVal]) => {
    const sel = document.getElementById(`select-${key}`);
    const badge = document.getElementById(`badge-${key}`);
    if (sel && badge) {
      const update = () => {
        const isDefault =
          key === "loudness_target_lufs"
            ? parseFloat(sel.value) === -16.0
            : sel.value === defaultVal;
        badge.className = `setting-badge ${isDefault ? "badge-default" : "badge-custom"}`;
        badge.textContent = isDefault ? "System Default" : "Custom Override";
      };
      sel.addEventListener("change", update);
    }
  });

  // ── 4. Native Website Reset Confirmation Modal ──
  const resetModal = document.getElementById("reset-modal");
  const openResetBtn = document.getElementById("btn-open-reset-modal");
  const cancelModalBtn = document.getElementById("btn-cancel-modal");

  if (openResetBtn && resetModal) {
    openResetBtn.addEventListener("click", () => {
      resetModal.showModal();
    });
  }

  if (cancelModalBtn && resetModal) {
    cancelModalBtn.addEventListener("click", () => {
      resetModal.close();
    });
  }

  if (resetModal) {
    resetModal.addEventListener("click", (e) => {
      if (e.target === resetModal) {
        resetModal.close();
      }
    });
  }

  // ── 6. Auto-dismiss success/status alerts after 5 seconds ──
  const alerts = document.querySelectorAll(".admin-alert");
  if (alerts.length > 0) {
    setTimeout(() => {
      alerts.forEach((alert) => {
        alert.classList.add("alert-fade-out");
        setTimeout(() => alert.remove(), 400);
      });
    }, 5000);
  }
});
