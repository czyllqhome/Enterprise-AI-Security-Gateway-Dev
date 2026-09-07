from dataclasses import dataclass, field


@dataclass(slots=True)
class ExtractedSegmentPayload:
    location: str
    text: str
    page_number: int | None = None
    sheet_name: str | None = None
    slide_number: int | None = None
    source_kind: str = "text"

    def model_dump(self) -> dict:
        return {
            "location": self.location,
            "text": self.text,
            "page_number": self.page_number,
            "sheet_name": self.sheet_name,
            "slide_number": self.slide_number,
            "source_kind": self.source_kind,
        }


@dataclass(slots=True)
class VisualReviewUnit:
    location: str
    image_bytes: bytes


@dataclass(slots=True)
class ExtractedDocument:
    summary: str
    plain_text: str
    segments: list[ExtractedSegmentPayload] = field(default_factory=list)
    # Only a parser that enumerates all supported original content may certify this.
    coverage_complete: bool = False
    coverage_issues: list[str] = field(default_factory=list)
    visual_units: list[VisualReviewUnit] = field(default_factory=list)
