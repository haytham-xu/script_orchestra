"""
PDF Converter Controller
REST API endpoints for PDF conversion
"""
import os
import uuid
from urllib.parse import quote
from flask import request, send_file, jsonify
from flask_restx import Namespace, Resource
from werkzeug.utils import secure_filename
from extensions import restx_api
import config
from pdf_converter.service import PDFConverterService

ns = Namespace("")


@ns.route("/pdf-converter/pdf-to-images")
class PdfToImagesResource(Resource):
    def post(self):
        """Convert PDF to images"""
        if 'file' not in request.files:
            return {"error": "No file provided"}, 400

        pdf_file = request.files['file']

        if pdf_file.filename == '':
            return {"error": "No file selected"}, 400

        if not pdf_file.filename.lower().endswith('.pdf'):
            return {"error": "File must be a PDF"}, 400

        try:
            # Create unique output folder
            task_id = str(uuid.uuid4())
            output_folder = os.path.join(config.PDF_CONVERTER_TEMP_PATH, task_id)

            # Convert PDF to images
            service = PDFConverterService()
            image_paths = service.pdf_to_images(pdf_file, output_folder)

            # Generate URLs for the images
            image_urls = [
                f"{config.HOST_URL}/pdf-converter/file/{task_id}/{quote(os.path.basename(img_path))}"
                for img_path in image_paths
            ]

            # Also create a ZIP file for batch download
            zip_path = os.path.join(output_folder, 'images.zip')
            service.create_zip_archive(image_paths, zip_path)
            zip_url = f"{config.HOST_URL}/pdf-converter/file/{task_id}/{quote('images.zip')}"

            return jsonify({
                "taskId": task_id,
                "images": image_urls,
                "zipUrl": zip_url,
                "count": len(image_urls)
            })

        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/pdf-converter/images-to-pdf")
class ImagesToPdfResource(Resource):
    def post(self):
        """Convert images to PDF"""
        if 'files' not in request.files:
            return {"error": "No files provided"}, 400

        image_files = request.files.getlist('files')

        if not image_files or len(image_files) == 0:
            return {"error": "No files selected"}, 400

        # Get output filename from request
        output_filename = request.form.get('filename', 'output.pdf')
        if not output_filename.lower().endswith('.pdf'):
            output_filename += '.pdf'

        # Sanitize filename while preserving unicode characters
        output_filename = output_filename.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')

        # Validate all files are images
        allowed_extensions = ('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')
        for img_file in image_files:
            if not img_file.filename.lower().endswith(allowed_extensions):
                return {"error": f"Invalid file type: {img_file.filename}"}, 400

        try:
            # Create unique output folder
            task_id = str(uuid.uuid4())
            output_folder = os.path.join(config.PDF_CONVERTER_TEMP_PATH, task_id)
            os.makedirs(output_folder, exist_ok=True)

            # Convert images to PDF
            output_pdf_path = os.path.join(output_folder, output_filename)
            service = PDFConverterService()
            service.images_to_pdf(image_files, output_pdf_path)

            # Generate URL for the PDF
            pdf_url = f"{config.HOST_URL}/pdf-converter/file/{task_id}/{quote(output_filename)}"

            return jsonify({
                "taskId": task_id,
                "pdfUrl": pdf_url,
                "filename": output_filename
            })

        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/pdf-converter/file/<task_id>/<path:filename>")
class FileDownloadResource(Resource):
    def get(self, task_id, filename):
        """Download converted file"""
        from urllib.parse import unquote
        # Decode URL-encoded filename
        filename = unquote(filename)
        file_path = os.path.join(config.PDF_CONVERTER_TEMP_PATH, task_id, filename)

        if not os.path.exists(file_path):
            return {"error": "File not found"}, 404

        return send_file(file_path, as_attachment=True, download_name=filename)


@ns.route("/pdf-converter/folder-to-pdf")
class FolderToPdfResource(Resource):
    def post(self):
        """Convert all images in a folder (recursively) to PDF"""
        if 'folder' not in request.files:
            return {"error": "No folder provided"}, 400

        # Get all uploaded files
        uploaded_files = request.files.getlist('folder')

        if not uploaded_files or len(uploaded_files) == 0:
            return {"error": "No files selected"}, 400

        # Get folder name and output filename from request
        folder_name = request.form.get('folderName', 'folder')
        output_filename = request.form.get('filename', f"{folder_name}.pdf")

        if not output_filename.lower().endswith('.pdf'):
            output_filename += '.pdf'

        # Sanitize filename while preserving unicode characters
        # Remove only dangerous characters like / \ : * ? " < > |
        output_filename = output_filename.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')

        # Filter only image files
        image_extensions = ('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif', '.webp')

        try:
            # Create unique folders for uploaded files and output
            task_id = str(uuid.uuid4())
            temp_folder = os.path.join(config.PDF_CONVERTER_TEMP_PATH, task_id, 'uploaded')
            output_folder = os.path.join(config.PDF_CONVERTER_TEMP_PATH, task_id)
            os.makedirs(temp_folder, exist_ok=True)

            # Save uploaded files maintaining their relative paths and collect image paths in order
            saved_image_paths = []
            for idx, file in enumerate(uploaded_files):
                if file.filename:
                    # Check if it's an image file
                    if file.filename.lower().endswith(image_extensions):
                        # Normalize path separators to current OS and remove path traversal
                        # Convert both \ and / to the current OS separator
                        safe_filename = file.filename.replace('\\', os.sep).replace('/', os.sep).replace('..', '_')
                        # Preserve directory structure
                        file_path = os.path.join(temp_folder, safe_filename)
                        file_dir = os.path.dirname(file_path)
                        os.makedirs(file_dir, exist_ok=True)
                        file.save(file_path)
                        saved_image_paths.append(file_path)

            if not saved_image_paths:
                return {"error": "No image files found in the uploaded files"}, 400

            # Group files by their folder while preserving the order they were received
            from collections import OrderedDict
            from pdf_converter.flex_sort import flex_natsort

            folder_files = OrderedDict()
            folder_order = []  # Track the order folders appear

            for file_path in saved_image_paths:
                # Extract folder name from the beginning of the filename
                rel_path = os.path.relpath(file_path, temp_folder)
                folder_root = rel_path.split(os.sep)[0] if os.sep in rel_path else ""

                if folder_root not in folder_files:
                    folder_files[folder_root] = []
                    folder_order.append(folder_root)

                folder_files[folder_root].append(file_path)

            # Sort files within each folder using flex_natsort, but preserve folder order
            sorted_image_paths = []
            for folder_root in folder_order:
                # Get relative paths for sorting within this folder
                folder_paths = folder_files[folder_root]
                relative_paths = [os.path.relpath(f, temp_folder) for f in folder_paths]
                sorted_relative = flex_natsort(relative_paths)
                sorted_full = [os.path.join(temp_folder, rel) for rel in sorted_relative]
                sorted_image_paths.extend(sorted_full)

            # Convert images to PDF preserving the frontend's folder order
            output_pdf_path = os.path.join(output_folder, output_filename)
            service = PDFConverterService()
            service.files_to_pdf_preserve_order(sorted_image_paths, output_pdf_path)

            # Generate URL for the PDF
            pdf_url = f"{config.HOST_URL}/pdf-converter/file/{task_id}/{quote(output_filename)}"

            return jsonify({
                "taskId": task_id,
                "pdfUrl": pdf_url,
                "filename": output_filename
            })

        except Exception as e:
            return {"error": str(e)}, 500


@ns.route("/pdf-converter/merge-pdfs")
class MergePdfsResource(Resource):
    def post(self):
        """Merge multiple PDF files into one"""
        if 'files' not in request.files:
            return {"error": "No files provided"}, 400

        pdf_files = request.files.getlist('files')

        if not pdf_files or len(pdf_files) == 0:
            return {"error": "No files selected"}, 400

        # Get output filename from request
        output_filename = request.form.get('filename', 'merged.pdf')
        if not output_filename.lower().endswith('.pdf'):
            output_filename += '.pdf'

        # Sanitize filename while preserving unicode characters
        output_filename = output_filename.replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')

        # Validate all files are PDFs
        for pdf_file in pdf_files:
            if not pdf_file.filename.lower().endswith('.pdf'):
                return {"error": f"Invalid file type: {pdf_file.filename}. Only PDF files are allowed."}, 400

        try:
            # Create unique output folder
            task_id = str(uuid.uuid4())
            output_folder = os.path.join(config.PDF_CONVERTER_TEMP_PATH, task_id)
            os.makedirs(output_folder, exist_ok=True)

            # Merge PDFs
            output_pdf_path = os.path.join(output_folder, output_filename)
            service = PDFConverterService()
            service.merge_pdfs(pdf_files, output_pdf_path)

            # Generate URL for the merged PDF
            pdf_url = f"{config.HOST_URL}/pdf-converter/file/{task_id}/{output_filename}"

            return jsonify({
                "taskId": task_id,
                "pdfUrl": pdf_url,
                "filename": output_filename,
                "mergedCount": len(pdf_files)
            })

        except Exception as e:
            return {"error": str(e)}, 500


restx_api.add_namespace(ns)
