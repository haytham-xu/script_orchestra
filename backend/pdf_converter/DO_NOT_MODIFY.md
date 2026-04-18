⚠️ **INDEPENDENT MODULE - DO NOT MODIFY WITHOUT EXPLICIT NEED** ⚠️

This pdf_converter module is intentionally isolated and should NOT be modified when working on other tools/modules.

## Why This Protection?

This module lacks comprehensive E2E test coverage. Any unintended modifications could break functionality without immediate detection.

## What This Means

- **DO NOT** refactor shared code that this module depends on
- **DO NOT** modify files in this directory unless explicitly working on PDF conversion features
- **DO NOT** change the sorting algorithm (`flex_sort.py` / `flexSort.ts`) in this module

## Independent Copies

This module contains independent copies of shared utilities to ensure isolation:

- `backend/pdf_converter/flex_sort.py` - Independent copy of `basic/flex_sort.py`
- `script-orchestra/src/pdf_converter/utils/flexSort.ts` - Independent copy of `src/basic/flexSort.ts`

## When You Need to Modify

If you must modify this module:

1. Test thoroughly in both Windows and Mac environments
2. Verify all 4 conversion modes:
   - Folder → PDF (with multiple folders)
   - Images → PDF
   - Merge PDFs
   - PDF → Images
3. Test with Chinese characters in filenames
4. Test manual folder reordering
5. Test drag & drop functionality

## Configuration Dependencies

This module depends on:
- `backend/config.py` - `PDF_CONVERTER_TEMP_PATH` setting
- `backend/buffer/pdf_converter/` - Temporary file storage

If you need to refactor global config, ensure backward compatibility for these dependencies.

## Future Work

Consider adding E2E tests for this module to remove this protection in the future.
