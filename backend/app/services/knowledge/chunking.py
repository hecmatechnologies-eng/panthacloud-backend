import io
import re
from dataclasses import dataclass

import pypdf


@dataclass
class ExtractedChunk:
    chunk_index: int
    text: str
    page_number: int | None
    source_location: str | None
    token_count: int


def _split_into_chunks(
    text: str,
    page_number: int | None = None,
    source_location: str | None = None,
    target_chars: int = 500,
    overlap_chars: int = 100,
) -> list[tuple[str, int | None, str | None]]:
    """
    Split text into chunks aiming for ~target_chars with ~overlap_chars.
    Respects paragraph, sentence, and word boundaries.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    if len(cleaned) <= target_chars:
        return [(cleaned, page_number, source_location)]

    chunks: list[tuple[str, int | None, str | None]] = []
    start = 0
    total_len = len(cleaned)

    while start < total_len:
        end = start + target_chars
        if end >= total_len:
            chunk_text = cleaned[start:].strip()
            if chunk_text:
                chunks.append((chunk_text, page_number, source_location))
            break

        # Look for natural breakpoint near target
        # Priority: paragraph break (\n\n), sentence break (. / ! / ?), line break (\n), word space (' ')
        slice_to_search = cleaned[max(start, end - 80) : min(total_len, end + 80)]
        split_pos = -1

        # 1. Paragraph break
        p_idx = slice_to_search.rfind("\n\n")
        if p_idx != -1:
            split_pos = max(start, end - 80) + p_idx + 2
        else:
            # 2. Sentence break
            s_matches = list(re.finditer(r"[.!?]\s", slice_to_search))
            if s_matches:
                split_pos = max(start, end - 80) + s_matches[-1].end()
            else:
                # 3. Line break
                nl_idx = slice_to_search.rfind("\n")
                if nl_idx != -1:
                    split_pos = max(start, end - 80) + nl_idx + 1
                else:
                    # 4. Word boundary
                    space_idx = slice_to_search.rfind(" ")
                    if space_idx != -1:
                        split_pos = max(start, end - 80) + space_idx + 1

        if split_pos == -1 or split_pos <= start or split_pos > total_len:
            split_pos = end

        chunk_text = cleaned[start:split_pos].strip()
        if chunk_text:
            chunks.append((chunk_text, page_number, source_location))

        # Advance start with overlap
        next_start = split_pos - overlap_chars
        # Find nearest word boundary forward for next_start
        if next_start > start and next_start < total_len:
            while next_start < split_pos and not cleaned[next_start].isspace():
                next_start += 1
            while next_start < split_pos and cleaned[next_start].isspace():
                next_start += 1

        if next_start <= start:
            next_start = split_pos

        start = next_start

    return chunks


def extract_and_chunk_pdf(raw_bytes: bytes) -> tuple[str, list[ExtractedChunk]]:
    """Extract text from PDF using pypdf and generate chunks with page preservation."""
    stream = io.BytesIO(raw_bytes)
    reader = pypdf.PdfReader(stream)
    
    full_text_parts: list[str] = []
    all_chunk_tuples: list[tuple[str, int | None, str | None]] = []

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        page_text = page.extract_text() or ""
        page_text = page_text.replace("\r\n", "\n").strip()
        if page_text:
            full_text_parts.append(f"--- Page {page_num} ---\n{page_text}")
            page_chunks = _split_into_chunks(
                text=page_text,
                page_number=page_num,
                source_location=f"Page {page_num}",
                target_chars=500,
                overlap_chars=100,
            )
            all_chunk_tuples.extend(page_chunks)

    full_text = "\n\n".join(full_text_parts)
    chunks = [
        ExtractedChunk(
            chunk_index=idx,
            text=c[0],
            page_number=c[1],
            source_location=c[2],
            token_count=len(re.findall(r"\b\w+\b", c[0])),
        )
        for idx, c in enumerate(all_chunk_tuples)
    ]
    return full_text, chunks


def extract_and_chunk_markdown(raw_bytes: bytes) -> tuple[str, list[ExtractedChunk]]:
    """Extract text from Markdown and chunk with heading preservation."""
    text = raw_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n")
    lines = text.split("\n")

    sections: list[tuple[str, str]] = []  # (heading, content)
    current_heading = "Document Header"
    current_lines: list[str] = []

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    for line in lines:
        match = heading_pattern.match(line.strip())
        if match:
            if current_lines:
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    sections.append((current_heading, section_text))
                current_lines = []
            current_heading = f"Heading: {match.group(2).strip()}"
        else:
            current_lines.append(line)

    if current_lines:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append((current_heading, section_text))

    if not sections and text.strip():
        sections.append(("Document Content", text.strip()))

    all_chunk_tuples: list[tuple[str, int | None, str | None]] = []
    for heading, section_text in sections:
        section_chunks = _split_into_chunks(
            text=section_text,
            page_number=None,
            source_location=heading,
            target_chars=500,
            overlap_chars=100,
        )
        all_chunk_tuples.extend(section_chunks)

    chunks = [
        ExtractedChunk(
            chunk_index=idx,
            text=c[0],
            page_number=c[1],
            source_location=c[2],
            token_count=len(re.findall(r"\b\w+\b", c[0])),
        )
        for idx, c in enumerate(all_chunk_tuples)
    ]
    return text, chunks


def extract_and_chunk_plain_text(raw_bytes: bytes) -> tuple[str, list[ExtractedChunk]]:
    """Extract text from plain text and chunk by paragraph/sentence boundaries."""
    text = raw_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    all_chunk_tuples: list[tuple[str, int | None, str | None]] = []
    for idx, p in enumerate(paragraphs):
        p_chunks = _split_into_chunks(
            text=p,
            page_number=None,
            source_location=f"Paragraph {idx + 1}",
            target_chars=500,
            overlap_chars=100,
        )
        all_chunk_tuples.extend(p_chunks)

    if not all_chunk_tuples and text.strip():
        all_chunk_tuples = _split_into_chunks(
            text=text.strip(),
            page_number=None,
            source_location="General Content",
            target_chars=500,
            overlap_chars=100,
        )

    chunks = [
        ExtractedChunk(
            chunk_index=idx,
            text=c[0],
            page_number=c[1],
            source_location=c[2],
            token_count=len(re.findall(r"\b\w+\b", c[0])),
        )
        for idx, c in enumerate(all_chunk_tuples)
    ]
    return text, chunks


def extract_and_chunk(
    content_type: str,
    raw_bytes: bytes,
    filename: str,
) -> tuple[str, list[ExtractedChunk]]:
    """
    Unified extraction entrypoint based on MIME and filename.
    """
    norm_filename = filename.lower()
    if content_type == "application/pdf" or norm_filename.endswith(".pdf"):
        return extract_and_chunk_pdf(raw_bytes)
    elif content_type in ("text/markdown", "text/x-markdown") or norm_filename.endswith((".md", ".markdown")):
        return extract_and_chunk_markdown(raw_bytes)
    elif content_type == "text/plain" or norm_filename.endswith(".txt"):
        return extract_and_chunk_plain_text(raw_bytes)
    else:
        raise ValueError(f"Unsupported file format for extraction: {filename} ({content_type})")
