"""
PDF Converter Service
Core conversion logic between PDF and images
"""
import os
import tempfile
import zipfile
from typing import List, Tuple
from pdf2image import convert_from_path
from PIL import Image
from PyPDF2 import PdfMerger
from werkzeug.datastructures import FileStorage
from basic.flex_sort import flex_natsort


class PDFConverterService:
    """Service for PDF and image conversion operations"""

    @staticmethod
    def pdf_to_images(pdf_file: FileStorage, output_folder: str) -> List[str]:
        """
        Convert PDF to images

        Args:
            pdf_file: Uploaded PDF file
            output_folder: Directory to save output images

        Returns:
            List of image file paths
        """
        # Create output folder if not exists
        os.makedirs(output_folder, exist_ok=True)

        # Save uploaded PDF to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
            pdf_file.save(tmp_pdf.name)
            tmp_pdf_path = tmp_pdf.name

        try:
            # Convert PDF to images
            images = convert_from_path(tmp_pdf_path)

            # Save each page as image
            image_paths = []
            for i, image in enumerate(images):
                image_path = os.path.join(output_folder, f'page_{i + 1}.png')
                image.save(image_path, 'PNG')
                image_paths.append(image_path)

            return image_paths

        finally:
            # Clean up temporary PDF file
            if os.path.exists(tmp_pdf_path):
                os.unlink(tmp_pdf_path)

    @staticmethod
    def images_to_pdf(image_files: List[FileStorage], output_pdf_path: str) -> str:
        """
        Convert multiple images to a single PDF

        Args:
            image_files: List of uploaded image files
            output_pdf_path: Path to save output PDF

        Returns:
            Path to the output PDF file
        """
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

        images = []
        temp_paths = []

        try:
            # Save uploaded images to temporary files and open them
            for image_file in image_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image_file.filename)[1]) as tmp_img:
                    image_file.save(tmp_img.name)
                    temp_paths.append(tmp_img.name)

                    # Open image and convert RGBA to RGB if needed
                    img = Image.open(tmp_img.name)
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    images.append(img)

            # Save all images as a single PDF
            if images:
                images[0].save(output_pdf_path, save_all=True, append_images=images[1:])
                return output_pdf_path
            else:
                raise ValueError("No images provided")

        finally:
            # Clean up temporary image files
            for temp_path in temp_paths:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    @staticmethod
    def create_zip_archive(file_paths: List[str], zip_path: str) -> str:
        """
        Create a ZIP archive from multiple files

        Args:
            file_paths: List of file paths to archive
            zip_path: Path to save ZIP file

        Returns:
            Path to the ZIP file
        """
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in file_paths:
                zipf.write(file_path, os.path.basename(file_path))
        return zip_path

    @staticmethod
    def collect_images_from_folder(folder_path: str) -> List[str]:
        """
        Recursively collect all image files from a folder and its subfolders

        Args:
            folder_path: Path to the folder

        Returns:
            Sorted list of image file paths
        """
        image_extensions = ('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif', '.webp')
        image_files = []

        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(image_extensions):
                    image_files.append(os.path.join(root, file))

        # Sort using flex_natsort for better ordering
        # Get relative paths for sorting
        relative_paths = [os.path.relpath(f, folder_path) for f in image_files]
        sorted_relative = flex_natsort(relative_paths)
        sorted_full_paths = [os.path.join(folder_path, rel) for rel in sorted_relative]

        return sorted_full_paths

    @staticmethod
    def folder_images_to_pdf(folder_path: str, output_pdf_path: str, folder_name: str = None) -> str:
        """
        Convert all images in a folder (including subfolders) to a single PDF

        Args:
            folder_path: Path to the folder containing images
            output_pdf_path: Path to save output PDF
            folder_name: Name of the folder (for default filename)

        Returns:
            Path to the output PDF file
        """
        # Collect all images
        image_paths = PDFConverterService.collect_images_from_folder(folder_path)

        if not image_paths:
            raise ValueError("No images found in the folder")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

        images = []
        try:
            # Open all images
            for image_path in image_paths:
                img = Image.open(image_path)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                images.append(img)

            # Save all images as a single PDF
            if images:
                images[0].save(output_pdf_path, save_all=True, append_images=images[1:])
                return output_pdf_path
            else:
                raise ValueError("No valid images to convert")

        finally:
            # Close all opened images
            for img in images:
                try:
                    img.close()
                except:
                    pass

    @staticmethod
    def files_to_pdf_preserve_order(file_paths: List[str], output_pdf_path: str) -> str:
        """
        Convert a list of image files to PDF, preserving the given order

        Args:
            file_paths: List of image file paths in the desired order
            output_pdf_path: Path to save output PDF

        Returns:
            Path to the output PDF file
        """
        if not file_paths:
            raise ValueError("No image files provided")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

        images = []
        try:
            # Open all images in the given order
            for file_path in file_paths:
                if os.path.exists(file_path):
                    img = Image.open(file_path)
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')
                    images.append(img)

            if not images:
                raise ValueError("No valid images to convert")

            # Save all images as a single PDF
            images[0].save(output_pdf_path, save_all=True, append_images=images[1:])
            return output_pdf_path

        finally:
            # Close all opened images
            for img in images:
                try:
                    img.close()
                except:
                    pass

    @staticmethod
    def merge_pdfs(pdf_files: List[FileStorage], output_pdf_path: str) -> str:
        """
        Merge multiple PDF files into a single PDF

        Args:
            pdf_files: List of uploaded PDF files
            output_pdf_path: Path to save merged PDF

        Returns:
            Path to the merged PDF file
        """
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

        temp_paths = []
        merger = PdfMerger()

        try:
            # Save uploaded PDFs to temporary files
            for pdf_file in pdf_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
                    pdf_file.save(tmp_pdf.name)
                    temp_paths.append(tmp_pdf.name)
                    merger.append(tmp_pdf.name)

            # Write merged PDF
            merger.write(output_pdf_path)
            merger.close()

            return output_pdf_path

        finally:
            # Clean up temporary PDF files
            for temp_path in temp_paths:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
