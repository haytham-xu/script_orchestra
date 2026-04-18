# PDF Converter Module

⚠️ **INDEPENDENT MODULE - Protected from unintended modifications** ⚠️
See [DO_NOT_MODIFY.md](./DO_NOT_MODIFY.md) for important isolation guidelines.

## Overview
PDF Converter is a comprehensive web-based tool for PDF and image conversion, supporting batch processing with intelligent sorting. This module was migrated from legacy scripts (`pdf_to_img.py`, `img_pdf.py`) to a modern full-stack architecture.

## Features

### 1. Folder → PDF (Default Mode)
- **Batch Queue System**: Add multiple folders to a queue before converting
- **Drag & Drop**: Directly drag folders from file manager into browser
- **Recursive Processing**: Automatically includes all images from subfolders
- **Intelligent Sorting**:
  - Frontend: Uses `flexNatsort` (TypeScript) to auto-sort folders by name
  - Backend: Uses `flex_natsort` (Python) to sort files within each folder
  - Supports Chinese numbers (一~二十, including traditional/uppercase forms)
  - Preserves folder order as arranged in UI (manual adjustment supported)
- **Manual Reordering**: Up/Down buttons to adjust folder order before conversion
- **Auto-Download**: Automatically downloads PDF after conversion
- **Unicode Filenames**: Full support for Chinese and special characters in filenames

### 2. Images → PDF
- Upload multiple image files
- Converts to a single PDF
- Auto-download on completion

### 3. Merge PDFs
- Select 2+ PDF files
- Merges into a single PDF
- Auto-download on completion

### 4. PDF → Images
- Convert PDF pages to individual images
- Downloads as ZIP file containing all images
- Auto-download on completion

## Technical Stack

### Frontend
- **Framework**: Vue 3 + TypeScript
- **UI Library**: Element Plus
- **Features**:
  - Drag & Drop API for folder uploads
  - Natural sorting with Chinese number support
  - Reactive queue management
  - Auto-download on success

### Backend
- **Framework**: Flask + Flask-RESTX
- **Libraries**:
  - `pdf2image`: PDF → Images conversion
  - `Pillow (PIL)`: Image processing and PDF generation
  - `PyPDF2`: PDF merging
  - `flex_natsort`: Intelligent sorting (supports Chinese numbers)
- **Features**:
  - RESTful API endpoints
  - Multipart/form-data file uploads
  - Cross-platform path handling (Windows/Mac/Linux)
  - Unicode filename support with URL encoding

## File Structure

```
backend/pdf_converter/
├── README.md           # This file (for AI context)
├── DO_NOT_MODIFY.md    # ⚠️ Module isolation guidelines
├── __init__.py
├── controller.py       # REST API endpoints
├── service.py          # Core conversion logic
├── flex_sort.py        # 🔒 Independent copy of basic/flex_sort.py

script-orchestra/src/pdf_converter/
├── views/
│   ├── PdfConverterView.vue  # Main UI component
│   └── PdfConverterView.ts   # Component logic
├── service/
│   ├── PdfConverterService.ts  # API calls
│   └── Model.ts                # Response types
└── utils/
    └── flexSort.ts             # 🔒 Independent copy of src/basic/flexSort.ts

backend/basic/
└── flex_sort.py        # Shared version (DO NOT use in pdf_converter)

script-orchestra/src/basic/
└── flexSort.ts         # Shared version (DO NOT use in pdf_converter)
```

**🔒 Independent Copies**: The files marked with 🔒 are independent copies to ensure module stability without E2E test coverage. Modifications to shared versions will NOT affect this module.

## Configuration

### Backend Config (`backend/config.py`)
```python
# Temporary files are stored in project's buffer folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_CONVERTER_TEMP_PATH = os.path.join(BASE_DIR, 'buffer', 'pdf_converter')
```

### Git Ignore
The `buffer/` folder is ignored in `.gitignore` to prevent tracking temporary files:
```
buffer/
```

Users can manually clean the buffer folder when needed.

## API Endpoints

### 1. PDF to Images
- **POST** `/pdf-converter/pdf-to-images`
- **Body**: `multipart/form-data`
  - `file`: PDF file
- **Response**:
  ```json
  {
    "taskId": "uuid",
    "images": ["url1", "url2", ...],
    "zipUrl": "url_to_zip",
    "count": 10
  }
  ```

### 2. Images to PDF
- **POST** `/pdf-converter/images-to-pdf`
- **Body**: `multipart/form-data`
  - `files`: Image files (multiple)
  - `filename`: Output PDF filename
- **Response**:
  ```json
  {
    "taskId": "uuid",
    "pdfUrl": "url",
    "filename": "output.pdf"
  }
  ```

### 3. Folder to PDF (Batch Mode)
- **POST** `/pdf-converter/folder-to-pdf`
- **Body**: `multipart/form-data`
  - `folder`: Files with relative paths (multiple)
  - `folderName`: Base folder name
  - `filename`: Output PDF filename
- **Response**:
  ```json
  {
    "taskId": "uuid",
    "pdfUrl": "url",
    "filename": "output.pdf"
  }
  ```

### 4. Merge PDFs
- **POST** `/pdf-converter/merge-pdfs`
- **Body**: `multipart/form-data`
  - `files`: PDF files (multiple)
  - `filename`: Output PDF filename
- **Response**:
  ```json
  {
    "taskId": "uuid",
    "pdfUrl": "url",
    "filename": "merged.pdf",
    "mergedCount": 3
  }
  ```

### 5. File Download
- **GET** `/pdf-converter/file/<task_id>/<path:filename>`
- Downloads the converted file

## Sorting Algorithm

### Frontend: `flexNatsort` (TypeScript)
Located in `/script-orchestra/src/basic/flexSort.ts`

**Features:**
- Natural number sorting (1, 2, 10 instead of 1, 10, 2)
- Chinese number recognition (一~二十)
- Case-insensitive comparison
- Used for auto-sorting folder queue

**Example:**
```typescript
flexNatsort(['folder三', 'folder一', 'folder二'])
// Returns: ['folder一', 'folder二', 'folder三']
```

### Backend: `flex_natsort` (Python)
Located in `/backend/basic/flex_sort.py`

**Features:**
- Powered by `natsort` library
- Chinese number recognition (一~二十, 壹~玖, 拾)
- Handles complex paths and filenames
- Used for sorting files within each folder

**Example:**
```python
flex_natsort(['img_10.png', 'img_2.png', 'img_一.png'])
# Returns: ['img_一.png', 'img_2.png', 'img_10.png']
```

## Implementation Details

### Cross-Platform Path Handling
```python
# Backend normalizes path separators to OS-specific
safe_filename = file.filename.replace('\\', os.sep).replace('/', os.sep)
```

### Unicode Filename Support
```python
# Sanitize while preserving Unicode characters
output_filename = output_filename.replace('/', '_').replace('\\', '_')...
# URL encode for transmission
pdf_url = f"{HOST_URL}/file/{task_id}/{quote(output_filename)}"
```

### Folder Order Preservation
```python
# Backend preserves frontend's folder order
folder_files = OrderedDict()
folder_order = []  # Tracks order folders appear in upload

for file_path in saved_image_paths:
    folder_root = extract_folder_name(file_path)
    if folder_root not in folder_files:
        folder_order.append(folder_root)
    folder_files[folder_root].append(file_path)

# Sort files within each folder, but preserve folder order
for folder_root in folder_order:
    sorted_files = flex_natsort(folder_files[folder_root])
    final_list.extend(sorted_files)
```

## Dependencies

### Backend
```txt
pdf2image==1.17.0
Pillow==11.1.0
PyPDF2==3.0.1
```

**System Dependencies:**
- `poppler-utils` (for pdf2image)
  - Mac: `brew install poppler`
  - Ubuntu: `apt-get install poppler-utils`
  - Windows: Download from poppler website

### Frontend
- Vue 3
- Element Plus
- TypeScript

## Migration Notes

### Migrated From
- `temp1/02_toolsbox/pdf_to_img.py` (basic PDF ↔ Images conversion)
- `temp1/02_toolsbox/04_script/img_pdf.py` (images to PDF)

**Status**: Moved to `temp1/trash/`

### Not Migrated
- `combine_image.py` - Different functionality (vertical image concatenation)

### Key Changes
1. ✅ CLI scripts → Web-based UI with REST API
2. ✅ Single folder → Batch queue with multiple folders
3. ✅ Basic sorting → Intelligent flex_natsort (Chinese number support)
4. ✅ Hardcoded paths → Configuration + drag & drop
5. ✅ Manual download → Auto-download on completion
6. ✅ ASCII only → Full Unicode support
7. ✅ Platform-specific → Cross-platform (Windows/Mac/Linux)

## Usage Example

### Frontend (Vue Component)
```typescript
// Add folders to queue (auto-sorted by flexNatsort)
addFolderToQueue(folderName, files)

// Manual reorder if needed
moveFolderUp(index)
moveFolderDown(index)

// Convert (respects UI order)
handleBatchFoldersToPdf()
```

### Backend (Service)
```python
# Preserve folder order from frontend
sorted_image_paths = []
for folder_root in folder_order:
    # Sort only within each folder
    folder_files = flex_natsort(files_in_folder)
    sorted_image_paths.extend(folder_files)

# Convert to PDF
files_to_pdf_preserve_order(sorted_image_paths, output_path)
```

## Future Enhancements

Potential improvements for future iterations:
- [ ] Progress bar for large conversions
- [ ] PDF page range selection for conversion
- [ ] Image quality/size options
- [ ] Batch download of multiple conversions
- [ ] Custom sorting options (by date, size, etc.)
- [ ] OCR support for scanned PDFs
- [ ] Password-protected PDF support

## Notes for AI Context

This README is designed to help AI understand the module for future modifications:

1. **Sorting is critical**: The dual sorting (frontend + backend) ensures consistent results across platforms
2. **Folder order matters**: Frontend order must be preserved; only sort within folders
3. **Unicode support**: Always use URL encoding for filenames in responses
4. **Cross-platform**: Use `os.sep` for path separators, never hardcode `/` or `\`
5. **Auto-download**: All conversions auto-download on success (no manual download button click needed)
6. **Temp files**: Stored in `backend/buffer/pdf_converter/`, can be manually cleaned by user

When modifying this module, preserve these core behaviors to maintain consistency with user expectations.
