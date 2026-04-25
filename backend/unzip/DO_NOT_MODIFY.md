⚠️ **INDEPENDENT MODULE - DO NOT MODIFY WITHOUT EXPLICIT NEED** ⚠️

This unzip module is intentionally isolated and should NOT be modified when working on other tools/modules.

## Why This Protection?

This module lacks comprehensive E2E test coverage. Any unintended modifications could break functionality without immediate detection.

## What This Means

- **DO NOT** refactor shared code that this module depends on
- **DO NOT** modify files in this directory unless explicitly working on unzip features
- **DO NOT** change the extraction logic or password handling

## Independent Module

This module is completely self-contained with no shared dependencies to ensure isolation.

## When You Need to Modify

If you must modify this module:

1. Test thoroughly in both Windows, Mac and Linux environments
2. Verify all archive formats:
   - ZIP (with/without password, with Chinese filenames)
   - RAR (with/without password)
   - 7z (with/without password)
3. Test both input modes:
   - Single file path
   - Folder path (non-recursive scan)
4. Test conflict handling (duplicate folder names)
5. Test password list functionality
6. Verify Chinese filename handling (GBK encoding)
7. Verify `__MACOSX` folder removal
8. Verify UnRAR is installed on the target system

## Configuration Dependencies

This module depends on:
- `backend/unzip/config.py` - Default configuration
- `backend/unzip/config_local.py` - Local password list (not tracked in git)

## System Dependencies

- **UnRAR** (required for RAR support)
  - macOS: `brew install unrar`
  - Windows: Download from https://www.rarlab.com/rar_add.htm
  - Linux: `apt-get install unrar`

## Future Work

Consider adding E2E tests for this module to remove this protection in the future.
