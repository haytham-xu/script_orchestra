/**
 * PDF Converter Service
 * API calls for PDF conversion
 */

import axios from 'axios'
import { ElMessage } from 'element-plus'
import {
  BACKEND_BASE_URL,
  PDF_CONVERTER_ENDPOINT_PDF_TO_IMAGES,
  PDF_CONVERTER_ENDPOINT_IMAGES_TO_PDF,
  PDF_CONVERTER_ENDPOINT_FOLDER_TO_PDF,
  PDF_CONVERTER_ENDPOINT_MERGE_PDFS
} from '@/basic/Constants'
import type { PdfToImagesResponse, ImagesToPdfResponse, MergePdfsResponse } from './Model'

/**
 * Convert PDF to images
 */
export async function convertPdfToImages(pdfFile: File): Promise<PdfToImagesResponse> {
  const formData = new FormData()
  formData.append('file', pdfFile)

  try {
    const res = await axios.post(
      BACKEND_BASE_URL + PDF_CONVERTER_ENDPOINT_PDF_TO_IMAGES,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )

    if (res.status === 200) {
      ElMessage.success('PDF converted successfully!')
      return res.data as PdfToImagesResponse
    } else {
      ElMessage.error(`Conversion failed: ${res.statusText}`)
      throw new Error(`Conversion failed: ${res.statusText}`)
    }
  } catch (error: any) {
    const errorMsg = error.response?.data?.error || error.message || 'Unknown error'
    ElMessage.error(`Conversion failed: ${errorMsg}`)
    throw error
  }
}

/**
 * Convert images to PDF
 */
export async function convertImagesToPdf(
  imageFiles: File[],
  filename: string = 'output.pdf'
): Promise<ImagesToPdfResponse> {
  const formData = new FormData()

  // Append all image files
  imageFiles.forEach((file) => {
    formData.append('files', file)
  })

  // Append filename
  formData.append('filename', filename)

  try {
    const res = await axios.post(
      BACKEND_BASE_URL + PDF_CONVERTER_ENDPOINT_IMAGES_TO_PDF,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )

    if (res.status === 200) {
      ElMessage.success('PDF created successfully!')
      return res.data as ImagesToPdfResponse
    } else {
      ElMessage.error(`Conversion failed: ${res.statusText}`)
      throw new Error(`Conversion failed: ${res.statusText}`)
    }
  } catch (error: any) {
    const errorMsg = error.response?.data?.error || error.message || 'Unknown error'
    ElMessage.error(`Conversion failed: ${errorMsg}`)
    throw error
  }
}

/**
 * Convert folder images to PDF
 */
export async function convertFolderToPdf(
  files: File[],
  folderName: string,
  filename?: string
): Promise<ImagesToPdfResponse> {
  const formData = new FormData()

  // Append all files from folder
  files.forEach((file) => {
    formData.append('folder', file, file.webkitRelativePath || file.name)
  })

  // Append folder name and filename
  formData.append('folderName', folderName)
  formData.append('filename', filename || `${folderName}.pdf`)

  try {
    const res = await axios.post(
      BACKEND_BASE_URL + PDF_CONVERTER_ENDPOINT_FOLDER_TO_PDF,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )

    if (res.status === 200) {
      ElMessage.success('Folder converted to PDF successfully!')
      return res.data as ImagesToPdfResponse
    } else {
      ElMessage.error(`Conversion failed: ${res.statusText}`)
      throw new Error(`Conversion failed: ${res.statusText}`)
    }
  } catch (error: any) {
    const errorMsg = error.response?.data?.error || error.message || 'Unknown error'
    ElMessage.error(`Conversion failed: ${errorMsg}`)
    throw error
  }
}

/**
 * Merge multiple PDFs
 */
export async function mergePdfs(
  pdfFiles: File[],
  filename: string = 'merged.pdf'
): Promise<MergePdfsResponse> {
  const formData = new FormData()

  // Append all PDF files
  pdfFiles.forEach((file) => {
    formData.append('files', file)
  })

  // Append filename
  formData.append('filename', filename)

  try {
    const res = await axios.post(
      BACKEND_BASE_URL + PDF_CONVERTER_ENDPOINT_MERGE_PDFS,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )

    if (res.status === 200) {
      ElMessage.success('PDFs merged successfully!')
      return res.data as MergePdfsResponse
    } else {
      ElMessage.error(`Merge failed: ${res.statusText}`)
      throw new Error(`Merge failed: ${res.statusText}`)
    }
  } catch (error: any) {
    const errorMsg = error.response?.data?.error || error.message || 'Unknown error'
    ElMessage.error(`Merge failed: ${errorMsg}`)
    throw error
  }
}
