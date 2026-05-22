"""Batch generation worker using QThread pattern for non-blocking UI."""
from PySide6.QtCore import QObject, QThread, Signal

from api_client import Flow2ApiClient, GenerationResult


class BatchGenerationManager(QObject):
    """Manages sequential batch generation, one request at a time.

    For local CDP mode, pass cdp_host/cdp_port and the worker thread will
    create its own GeminiCDPClient (Playwright is not thread-safe, so the
    client must be created in the worker thread, not the main thread).
    """

    item_started = Signal(int)
    item_finished = Signal(int, GenerationResult)
    batch_progress = Signal(int, int)  # done, total
    all_finished = Signal()

    def __init__(self, client: Flow2ApiClient | None = None,
                 cdp_host: str = "", cdp_port: int = 9222):
        super().__init__()
        self.client = client
        self._cdp_host = cdp_host
        self._cdp_port = cdp_port
        self._thread: QThread | None = None
        self._runner: _BatchRunner | None = None

    def start_batch(self, prompts: list[str], model: str, image_size: str = ""):
        """Start sequential batch generation (0-indexed, no reference images)."""
        items = [(i, p, None) for i, p in enumerate(prompts)]
        self._start(items, model, image_size)

    def start_indexed_batch(self, items: list[tuple[int, str, bytes | None]], model: str,
                            image_size: str = ""):
        """Start batch with explicit (index, prompt, reference_image) tuples."""
        self._start(items, model, image_size)

    def start_single(self, index: int, prompt: str, model: str, reference_image: bytes | None = None,
                     image_size: str = ""):
        """Generate a single prompt, emitting signals with the given card index."""
        self._start([(index, prompt, reference_image)], model, image_size)

    def _start(self, items: list[tuple[int, str, bytes | None]], model: str, image_size: str):
        # Clean up previous thread if still lingering
        if self._thread is not None and self._thread.isRunning():
            self._runner.cancel()
            self._thread.quit()
            self._thread.wait(1000)
        self._runner = _BatchRunner(self.client, items, model, image_size,
                                    cdp_host=self._cdp_host, cdp_port=self._cdp_port)
        self._thread = QThread()
        self._runner.moveToThread(self._thread)
        self._wire_runner(self._runner)
        self._thread.started.connect(self._runner.run)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _wire_runner(self, runner):
        runner.item_started.connect(self.item_started)
        runner.item_finished.connect(self.item_finished)
        runner.batch_progress.connect(self.batch_progress)
        runner.all_finished.connect(self.all_finished)
        runner.all_finished.connect(self._thread.quit)

    def _on_thread_finished(self):
        if self._thread:
            self._thread.wait(500)
            self._thread.deleteLater()
            self._thread = None

    def cancel(self):
        """Cancel the current batch."""
        if self._runner:
            self._runner.cancel()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()


class _BatchRunner(QObject):
    """Generates prompts with explicit card indices and optional per-item reference images.

    In local CDP mode (cdp_host is set), creates a fresh GeminiCDPClient in the
    worker thread because Playwright objects are bound to their creation thread.
    """
    item_started = Signal(int)
    item_finished = Signal(int, GenerationResult)
    batch_progress = Signal(int, int)
    all_finished = Signal()

    def __init__(self, client: Flow2ApiClient | None, items: list[tuple[int, str, bytes | None]],
                 model: str, image_size: str = "",
                 cdp_host: str = "", cdp_port: int = 9222):
        super().__init__()
        self.client = client
        self.items = items  # (index, prompt, reference_image)
        self.model = model
        self.image_size = image_size
        self._cdp_host = cdp_host
        self._cdp_port = cdp_port
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        # Local CDP mode: create a thread-local client so Playwright objects
        # are owned by this worker thread, not the main/GUI thread.
        cdp_client = None
        effective_client = self.client
        if self._cdp_host:
            from gemini_cdp import GeminiCDPClient
            cdp_client = GeminiCDPClient(chrome_host=self._cdp_host,
                                         chrome_port=self._cdp_port,
                                         timeout=300)
            effective_client = cdp_client

        try:
            total = len(self.items)
            for i, (index, prompt, ref_img) in enumerate(self.items):
                if self._cancelled:
                    break
                self.item_started.emit(index)
                result = effective_client.generate_image(prompt, self.model, ref_img, self.image_size)
                self.item_finished.emit(index, result)
                self.batch_progress.emit(i + 1, total)
        finally:
            # Clean up Playwright's greenlet/event loop before thread exits.
            # disconnect() only stops Playwright; it does NOT close the browser
            # page, so the user can continue editing images on Gemini.
            if cdp_client is not None:
                try:
                    cdp_client.disconnect()
                except Exception:
                    pass
        self.all_finished.emit()
