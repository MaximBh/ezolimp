"""Shared synchronization for PDFium's process-global native state."""

from threading import RLock


# PDFium is not thread-safe, even when each thread uses a different document.
# RLock is required because rendering can call the PDF parser recursively.
pdfium_lock = RLock()
