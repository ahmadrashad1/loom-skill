"""OBS Studio control over obs-websocket v5 (built into OBS 28+).

Optional: only used with `recorder: obs` for full-desktop demonstrations.
Install with `uv sync --extra obs`.
"""

from __future__ import annotations

import time

CAMERA_KINDS = {"v4l2_input", "av_capture_input", "dshow_input", "pipewire-camera-source"}


class OBSError(RuntimeError):
    pass


class OBS:
    def __init__(self, host: str, port: int, password: str | None):
        try:
            import obsws_python as obsws
        except ImportError as e:
            raise OBSError("obsws-python missing: run `uv sync --extra obs`") from e
        try:
            self.cl = obsws.ReqClient(host=host, port=port, password=password or "", timeout=5)
        except Exception as e:
            raise OBSError(
                f"cannot reach OBS at {host}:{port}. Start OBS and enable "
                "Tools → WebSocket Server Settings.") from e

    def version(self) -> str:
        return self.cl.get_version().obs_version

    def assert_no_camera(self) -> None:
        inputs = self.cl.get_input_list().inputs
        cams = [i["inputName"] for i in inputs if i.get("inputKind") in CAMERA_KINDS]
        if cams:
            raise OBSError(f"OBS has camera sources {cams}; remove them (no-webcam rule)")

    def start(self) -> None:
        if self.cl.get_record_status().output_active:
            raise OBSError("OBS is already recording")
        self.cl.start_record()
        for _ in range(50):
            if self.cl.get_record_status().output_active:
                return
            time.sleep(0.1)
        raise OBSError("OBS did not start recording")

    def stop(self) -> str | None:
        try:
            return self.cl.stop_record().output_path
        except Exception:
            return None
