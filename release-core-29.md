# Karel 2.0.0-alpha.29 – Core workflow

## Scope
1. Chat: Preserve existing project chat, history and AI Engine integration. The same input goes through one response pipeline unless a narrowly scoped explicit write can be resolved deterministically.
2. Write: The model proposes a whitelisted `KAREL_STATE` action, the user approves it, and the executor writes and verifies the authoritative database state. Long project briefs don't trigger the keyword writer. No automatic production operation.
3. Files: New `attachment_reader.py` performs bounded extraction of text, source ZIP, PDF (pypdf) and DOCX; the extracted content enters AI context. Archives are never extracted to disk nor code executed. ZIP source inventory, bounded source samples, and honest errors when the content cannot be read. Metadata-only analysis is no longer presented as reading the file.

## Proven by local tests
- Login, project creation and chat request using a stub AI Engine.
- An actual ZIP upload, real file text retrieved and included in AI context.
- Prompt with a long brief does not directly create a pending write.
- AI-proposed change creates a pending action; one approval leads to verified DB value, with no remaining pending group.
- DOCX extraction, PDF text fallback and redaction of common credentials.
- Python compilation and Jinja template parse.

## Not verified
- Live production Exon.io/Passenger operation; real Fresh AI Engine output limits, timeouts and server stack trace.
- OCR, scanned images, sophisticated semantic segmentation of large multi-file sources.
- The server's existing alpha.28 crash cannot be conclusively diagnosed without its error log.

## Installation
Full replacement of application files from the ZIP, but preserve original `.env`, `storage/`, database and existing virtual environment. Install new requirements (`pypdf`) and restart Passenger. Keep a full backup and test on staging before production.
