# How to read this project's source material — read this before you summarise anything

The owner's trading material (decks, a book, 48 video frames, screenshots) is **the specification**. Whether
you have read it is the first thing the owner will ask, and they check. Four sessions' worth of claims in this
repo turned out to rest on images that were never seen. This page is how not to do that again.

## The rules

1. **Look at the pages. Do not read extracted text and call it reading.** The owner's words: *take the PDFs as
   screenshots and actually read them, not texts.* These decks are image-only (no text layer at all), so text
   extraction returns nothing, and even where a text layer exists (the Candlestick Bible) the charts and
   arrows carry rules the text does not. Render to PNG and view it with the Read tool.
2. **A tool result that says `[media removed: request limit]` is a failed read.** It is not an empty page and
   it is not "seen". Say so, retry in smaller batches, and never write "I read it" on the strength of it.
   This happened here four times in a row, each time reported as success.
3. **Count a page as read only when an image came back.** Say exactly which pages you viewed and which you
   did not. "Read all 48" is a claim the owner will test against your output.
4. **Do not write a rule from a spec sentence, a prior agent's note, or your own memory of the image.** Open
   the picture and measure it (`docs/smc/spec.md` measured frames in pixels). Three corrections were needed
   in `docs/smc/` because earlier notes had not been checked against the frames.
5. **Re-check the earlier agent's claim against the picture before building on it.** Prior notes are leads,
   not evidence.

## How

| Material | Command | Notes |
|---|---|---|
| Image-only PDF (the decks) | `python3 docs/sources/tools/pdf_pages_to_png.py deck.pdf out_dir` | Needs `PyPDF2` from the system `python3` (not the venv). ~30 s for 15 pages. Decodes the raw image streams; PyPDF2's own `page.images` export returns noise for these files. |
| Ordinary PDF (the Candlestick Bible) | `swiftc -O docs/sources/tools/render_pdf_pages.swift -o /tmp/render && /tmp/render book.pdf out_dir 16 17 81` | macOS PDFKit, no install. Page numbers are 1-based. |
| The 48 frames | unzip `DAILY_TRADING_CONCEPTS.zip`; each `S01.png`-`S48.png` is already an image | Pixel rows can be measured with Pillow from the system python (`from PIL import Image`). |

What is **not** installed on the owner's Mac: `pdftotext`, `pdftoppm`/poppler, `mutool`, `fitz`, `pypdf`. Do not
spend a turn rediscovering that. Put scratch renders in your scratchpad directory, not in the repo.

Then **view them in small batches** (four to eight per call), and look at what came back before the next batch.

## Where the owner keeps it

`~/Desktop/Trading/` holds the six deck PDFs, `DIGITS.zip`, `THE CANDLESTICK TRADING BIBLE.pdf` and
`SMC_Trading_Architecture.pdf`; `~/Desktop/DAILY_TRADING_CONCEPTS.zip` holds the video frames. The owner
generated the decks themselves (NotebookLM) from courses and videos they hold. They are not committed: the
underlying courses are not the owner's, and the repo is public. `docs/sources/<deck>/pNN.md` is the committed
description of each page, in this project's words.

## How the owner wants sessions run (learned the hard way; also in `memory/user/preferences.md`)

- **A session opened for a task means do the task.** Do not stop to ask whether to continue it, or which half
  to do. The owner's response to exactly that was: *why ask, I initiated this session especially for this.*
- **Fix everything in scope, in phases, including the ADR.** Record the decision; do not just patch.
- **Verification means first-hand.** If you were asked to check someone's work, open their sources, not their
  summary of them.
- **Say what failed.** An overstated "I read it" costs far more trust than "that read failed, retrying".
- **The engine imitates a person's reading of the chart** (`docs/smc/README.md`): implement what the source
  states, decode comparative words as comparisons against the chart's own window, mark the rest absent. Look
  at the picture (`clicktrader smc-chart`) before and after changing a detection rule.
- Short progress lines while working; final report leads with what changed and what is still unverified.
