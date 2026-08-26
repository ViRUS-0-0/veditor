"""Background tasks and RQ job functions for VEditor pipeline.

This module houses stage wrapper functions dispatched via RQ.
Worker processes eagerly import this module at boot to avoid per-job import overhead.
"""
