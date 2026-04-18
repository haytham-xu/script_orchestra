# PDF Converter Module

## Overview
A web-based tool for converting between PDF and image formats.

## Features

### PDF to Images
- Convert PDF files to PNG images (one image per page)
- Preview all converted images
- Download individual images or all as ZIP

### Images to PDF
- Combine multiple images into a single PDF
- Support for: PNG, JPG, JPEG, BMP, GIF, TIFF
- Drag-and-drop file upload
- Custom output filename

## Dependencies

### Backend (Python)
```bash
pip install pdf2image Pillow
```

**Note**: `pdf2image` requires `poppler` to be installed:
- **macOS**: `brew install poppler`
- **Linux**: `sudo apt-get install poppler-utils`
- **Windows**: Download from [poppler releases](https://github.com/oschwartz10612/poppler-windows/releases/)

### Frontend (Vue 3)
All dependencies are already included in the project's `package.json`.

## Configuration

### Backend Config
In `backend/config.py`:
```python
PDF_CONVERTER_TEMP_PATH = '/tmp/pdf_converter'  # Temporary file storage
```

For production, you may want to override this in `config_local.py`:
```python
PDF_CONVERTER_TEMP_PATH = '/path/to/your/storage'
```

## API Endpoints

### POST `/pdf-converter/pdf-to-images`
Convert PDF to images.

**Request**:
- Content-Type: `multipart/form-data`
- Body: `file` (PDF file)

**Response**:
```json
{
  "taskId": "uuid",
  "images": ["url1", "url2", ...],
  "zipUrl": "url",
  "count": 5
}
```

### POST `/pdf-converter/images-to-pdf`
Convert images to PDF.

**Request**:
- Content-Type: `multipart/form-data`
- Body:
  - `files` (multiple image files)
  - `filename` (output PDF name)

**Response**:
```json
{
  "taskId": "uuid",
  "pdfUrl": "url",
  "filename": "output.pdf"
}
```

### GET `/pdf-converter/file/<task_id>/<filename>`
Download converted file.

## Usage

1. Navigate to `http://localhost:8080/pdf-converter`
2. Select conversion mode (PDF→Images or Images→PDF)
3. Upload file(s)
4. Click "Convert"
5. Download results

## File Structure

```
backend/pdf_converter/
├── __init__.py
├── controller.py      # REST API endpoints
├── service.py         # Core conversion logic
└── README.md

script-orchestra/src/pdf_converter/
├── service/
│   ├── Model.ts              # TypeScript interfaces
│   └── PdfConverterService.ts # API client
└── views/
    ├── PdfConverterView.ts   # Component logic
    └── PdfConverterView.vue  # Component template
```

## Migration Notes

This module was migrated from the following original scripts:
- `temp1/02_toolsbox/pdf_to_img.py` - PDF to images conversion
- `temp1/02_toolsbox/04_script/img_pdf.py` - Images to PDF conversion

### Key Changes:
1. ✅ CLI scripts → Web API
2. ✅ Local file paths → File upload/download
3. ✅ Hardcoded paths → Configuration
4. ✅ Single-purpose scripts → Unified module
5. ✅ Added error handling and validation
6. ✅ Added modern UI with drag-and-drop

## Future Enhancements
- [ ] Add PDF page selection (convert specific pages only)
- [ ] Add image quality/DPI settings
- [ ] Add PDF compression options
- [ ] Add batch processing queue
- [ ] Add conversion history
- [ ] Add progress indicator for large files
