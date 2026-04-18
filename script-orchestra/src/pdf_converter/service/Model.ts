/**
 * PDF Converter Data Models
 */

export interface PdfToImagesResponse {
  taskId: string
  images: string[]
  zipUrl: string
  count: number
}

export interface ImagesToPdfResponse {
  taskId: string
  pdfUrl: string
  filename: string
}

export interface MergePdfsResponse {
  taskId: string
  pdfUrl: string
  filename: string
  mergedCount: number
}

export interface ErrorResponse {
  error: string
}
