from pathlib import Path
import subprocess
from urllib.parse import quote

from ..core.config import get_settings


class OfficeRenderingService:
    def __init__(self, executable: str | None = None, timeout: int | None = None):
        settings = get_settings()
        self.executable = Path(executable or settings.office_converter_path).expanduser() if (executable or settings.office_converter_path) else None
        self.timeout = timeout or settings.office_converter_timeout

    def render_pdf(self, source: Path, output_directory: Path) -> Path:
        if self.executable is None or not self.executable.is_file():
            raise RuntimeError("An isolated Office converter has not been configured.")
        profile = output_directory / "profile"
        profile.mkdir()
        profile_uri = "file:///" + quote(str(profile.resolve()).replace("\\", "/"), safe="/: ").replace(" ", "%20")
        completed = subprocess.run([
            str(self.executable.resolve()), "--headless", "--nologo", "--nodefault", "--nolockcheck",
            f"-env:UserInstallation={profile_uri}", "--convert-to", "pdf", "--outdir",
            str(output_directory.resolve()), str(source.resolve()),
        ], check=False, capture_output=True, timeout=self.timeout, shell=False)
        rendered = output_directory / (source.stem + ".pdf")
        if completed.returncode != 0 or not rendered.is_file():
            raise RuntimeError("Office rendering failed.")
        return rendered
