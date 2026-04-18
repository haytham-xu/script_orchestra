import { defineComponent, ref, computed } from 'vue'
import {
  convertPdfToImages,
  convertImagesToPdf,
  convertFolderToPdf,
  mergePdfs
} from '@/pdf_converter/service/PdfConverterService'
import type { PdfToImagesResponse, ImagesToPdfResponse, MergePdfsResponse } from '@/pdf_converter/service/Model'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadUserFile } from 'element-plus'
import { flexNatsort } from '@/pdf_converter/utils/flexSort'

// Interface for folder queue item
interface FolderQueueItem {
  id: string
  name: string
  files: File[]
  fileCount: number
}

export default defineComponent({
  name: 'PdfConverterView',
  setup() {
    // Conversion mode: 'folder-to-pdf' is default, then 'images-to-pdf', 'merge-pdfs', 'pdf-to-images'
    const conversionMode = ref<'pdf-to-images' | 'images-to-pdf' | 'folder-to-pdf' | 'merge-pdfs'>('folder-to-pdf')

    // PDF to Images
    const pdfFile = ref<File | null>(null)
    const pdfToImagesResult = ref<PdfToImagesResponse | null>(null)
    const pdfToImagesLoading = ref(false)

    // Images to PDF
    const imageFiles = ref<File[]>([])
    const imagesToPdfResult = ref<ImagesToPdfResponse | null>(null)
    const imagesToPdfLoading = ref(false)
    const outputPdfFilename = ref('output.pdf')

    // Folder to PDF - Batch Queue Mode
    const folderQueue = ref<FolderQueueItem[]>([])
    const folderToPdfResult = ref<ImagesToPdfResponse | null>(null)
    const folderToPdfLoading = ref(false)
    const batchOutputFilename = ref('combined.pdf')
    const isDraggingOver = ref(false)

    // Computed properties for folder queue
    const totalFoldersInQueue = computed(() => folderQueue.value.length)
    const totalFilesInQueue = computed(() =>
      folderQueue.value.reduce((sum, item) => sum + item.fileCount, 0)
    )

    // Merge PDFs
    const mergePdfFiles = ref<File[]>([])
    const mergePdfsResult = ref<MergePdfsResponse | null>(null)
    const mergePdfsLoading = ref(false)
    const mergeOutputFilename = ref('merged.pdf')

    // Handle PDF file upload
    const handlePdfFileChange = (file: UploadFile) => {
      if (file.raw) {
        pdfFile.value = file.raw
        pdfToImagesResult.value = null
      }
      return false // Prevent auto upload
    }

    // Convert PDF to images
    const handlePdfToImages = async () => {
      if (!pdfFile.value) {
        ElMessage.warning('Please select a PDF file first')
        return
      }

      pdfToImagesLoading.value = true
      try {
        const result = await convertPdfToImages(pdfFile.value)
        pdfToImagesResult.value = result
        // Auto download ZIP file
        downloadFile(result.zipUrl)
      } catch (error) {
        console.error('PDF to Images conversion failed:', error)
      } finally {
        pdfToImagesLoading.value = false
      }
    }

    // Handle image files upload
    const handleImageFilesChange = (file: UploadFile, fileList: UploadUserFile[]) => {
      imageFiles.value = fileList.map((f) => f.raw).filter((f): f is File => f !== undefined)
      imagesToPdfResult.value = null
      return false // Prevent auto upload
    }

    // Remove image file
    const handleImageFileRemove = (file: UploadFile, fileList: UploadUserFile[]) => {
      imageFiles.value = fileList.map((f) => f.raw).filter((f): f is File => f !== undefined)
    }

    // Convert images to PDF
    const handleImagesToPdf = async () => {
      if (imageFiles.value.length === 0) {
        ElMessage.warning('Please select at least one image file')
        return
      }

      imagesToPdfLoading.value = true
      try {
        const result = await convertImagesToPdf(imageFiles.value, outputPdfFilename.value)
        imagesToPdfResult.value = result
        // Auto download PDF file
        downloadFile(result.pdfUrl)
      } catch (error) {
        console.error('Images to PDF conversion failed:', error)
      } finally {
        imagesToPdfLoading.value = false
      }
    }

    // Handle folder upload - Add to queue
    const handleAddFolder = (event: Event) => {
      const target = event.target as HTMLInputElement
      if (target.files) {
        const files = Array.from(target.files)

        if (files.length === 0) {
          ElMessage.warning('No files selected')
          return
        }

        // Extract folder name from first file's path
        let extractedFolderName = 'folder'
        if (files[0].webkitRelativePath) {
          const pathParts = files[0].webkitRelativePath.split('/')
          extractedFolderName = pathParts[0]
        }

        addFolderToQueue(extractedFolderName, files)

        // Reset file input
        target.value = ''
      }
    }

    // Helper function to add folder to queue
    const addFolderToQueue = (folderName: string, files: File[]) => {
      // Check if folder already exists in queue
      const existingFolder = folderQueue.value.find(item => item.name === folderName)
      if (existingFolder) {
        ElMessage.warning(`Folder "${folderName}" is already in the queue`)
        return
      }

      // Add to queue
      const queueItem: FolderQueueItem = {
        id: Date.now().toString() + Math.random(),
        name: folderName,
        files: files,
        fileCount: files.length
      }

      folderQueue.value.push(queueItem)

      // Sort queue by folder name using flex_natsort (same as backend)
      const folderNames = folderQueue.value.map(f => f.name)
      const sortedNames = flexNatsort(folderNames)

      // Reorder the queue based on sorted names
      const sortedQueue: FolderQueueItem[] = []
      sortedNames.forEach(name => {
        const item = folderQueue.value.find(f => f.name === name)
        if (item) sortedQueue.push(item)
      })
      folderQueue.value = sortedQueue

      ElMessage.success(`Added folder "${folderName}" to queue (${files.length} files)`)

      // Set output filename to first folder's name if this is the only folder
      if (folderQueue.value.length === 1) {
        batchOutputFilename.value = `${folderName}.pdf`
      }
    }

    // Drag and Drop handlers
    const handleDragOver = (event: DragEvent) => {
      event.preventDefault()
      isDraggingOver.value = true
    }

    const handleDragLeave = (event: DragEvent) => {
      event.preventDefault()
      isDraggingOver.value = false
    }

    const handleDrop = async (event: DragEvent) => {
      event.preventDefault()
      isDraggingOver.value = false

      const items = event.dataTransfer?.items
      if (!items) {
        ElMessage.warning('No items dropped')
        return
      }

      // Process each dropped item
      for (let i = 0; i < items.length; i++) {
        const item = items[i]
        if (item.kind === 'file') {
          const entry = item.webkitGetAsEntry()
          if (entry && entry.isDirectory) {
            await processDirectoryEntry(entry as FileSystemDirectoryEntry)
          }
        }
      }
    }

    // Recursively process directory entry
    const processDirectoryEntry = async (dirEntry: FileSystemDirectoryEntry) => {
      const files: File[] = []
      const folderName = dirEntry.name

      await readDirectory(dirEntry, files, dirEntry.name)

      if (files.length > 0) {
        addFolderToQueue(folderName, files)
      } else {
        ElMessage.warning(`Folder "${folderName}" contains no files`)
      }
    }

    // Recursively read all files from directory
    const readDirectory = async (dirEntry: FileSystemDirectoryEntry, filesList: File[], basePath: string): Promise<void> => {
      return new Promise((resolve, reject) => {
        const dirReader = dirEntry.createReader()

        const readEntries = () => {
          dirReader.readEntries(async (entries) => {
            if (entries.length === 0) {
              resolve()
              return
            }

            for (const entry of entries) {
              if (entry.isFile) {
                const fileEntry = entry as FileSystemFileEntry
                const file = await getFileFromEntry(fileEntry, basePath)
                if (file) {
                  filesList.push(file)
                }
              } else if (entry.isDirectory) {
                await readDirectory(entry as FileSystemDirectoryEntry, filesList, basePath)
              }
            }

            // Continue reading (directories with many files may need multiple reads)
            readEntries()
          }, reject)
        }

        readEntries()
      })
    }

    // Get File object from FileSystemFileEntry
    const getFileFromEntry = (fileEntry: FileSystemFileEntry, basePath: string): Promise<File | null> => {
      return new Promise((resolve) => {
        fileEntry.file((file) => {
          // Create a new File with webkitRelativePath set
          const relativePath = fileEntry.fullPath.substring(1) // Remove leading '/'
          const newFile = new File([file], file.name, {
            type: file.type,
            lastModified: file.lastModified,
          })
          // Manually set webkitRelativePath (read-only property workaround)
          Object.defineProperty(newFile, 'webkitRelativePath', {
            value: `${basePath}/${relativePath}`,
            writable: false
          })
          resolve(newFile)
        }, () => {
          resolve(null)
        })
      })
    }

    // Remove folder from queue
    const removeFolderFromQueue = (folderId: string) => {
      const index = folderQueue.value.findIndex(item => item.id === folderId)
      if (index !== -1) {
        const folderName = folderQueue.value[index].name
        folderQueue.value.splice(index, 1)
        ElMessage.info(`Removed folder "${folderName}" from queue`)
      }
    }

    // Move folder up in queue
    const moveFolderUp = (index: number) => {
      if (index > 0) {
        const temp = folderQueue.value[index]
        folderQueue.value[index] = folderQueue.value[index - 1]
        folderQueue.value[index - 1] = temp
      }
    }

    // Move folder down in queue
    const moveFolderDown = (index: number) => {
      if (index < folderQueue.value.length - 1) {
        const temp = folderQueue.value[index]
        folderQueue.value[index] = folderQueue.value[index + 1]
        folderQueue.value[index + 1] = temp
      }
    }

    // Clear all folders from queue
    const clearFolderQueue = () => {
      folderQueue.value = []
      ElMessage.info('Queue cleared')
    }

    // Convert all folders in queue to PDF
    const handleBatchFoldersToPdf = async () => {
      if (folderQueue.value.length === 0) {
        ElMessage.warning('Please add at least one folder to the queue')
        return
      }

      folderToPdfLoading.value = true
      try {
        // Combine all files from all folders
        const allFiles: File[] = []
        folderQueue.value.forEach(folder => {
          allFiles.push(...folder.files)
        })

        // Use the first folder's name as base, or use custom filename
        const baseFolderName = folderQueue.value.length === 1
          ? folderQueue.value[0].name
          : 'combined'

        const result = await convertFolderToPdf(
          allFiles,
          baseFolderName,
          batchOutputFilename.value
        )
        folderToPdfResult.value = result

        // Auto download PDF file
        downloadFile(result.pdfUrl)

        // Clear queue after successful conversion
        ElMessage.success(`Successfully converted ${totalFoldersInQueue.value} folders to PDF`)
      } catch (error) {
        console.error('Batch folders to PDF conversion failed:', error)
      } finally {
        folderToPdfLoading.value = false
      }
    }

    // Handle merge PDF files upload
    const handleMergePdfFilesChange = (file: UploadFile, fileList: UploadUserFile[]) => {
      mergePdfFiles.value = fileList.map((f) => f.raw).filter((f): f is File => f !== undefined)
      mergePdfsResult.value = null
      return false
    }

    // Remove merge PDF file
    const handleMergePdfFileRemove = (file: UploadFile, fileList: UploadUserFile[]) => {
      mergePdfFiles.value = fileList.map((f) => f.raw).filter((f): f is File => f !== undefined)
    }

    // Merge PDFs
    const handleMergePdfs = async () => {
      if (mergePdfFiles.value.length < 2) {
        ElMessage.warning('Please select at least 2 PDF files to merge')
        return
      }

      mergePdfsLoading.value = true
      try {
        const result = await mergePdfs(mergePdfFiles.value, mergeOutputFilename.value)
        mergePdfsResult.value = result
        // Auto download merged PDF file
        downloadFile(result.pdfUrl)
      } catch (error) {
        console.error('Merge PDFs failed:', error)
      } finally {
        mergePdfsLoading.value = false
      }
    }

    // Download file
    const downloadFile = (url: string) => {
      window.open(url, '_blank')
    }

    // Reset forms
    const resetPdfToImagesForm = () => {
      pdfFile.value = null
      pdfToImagesResult.value = null
    }

    const resetImagesToPdfForm = () => {
      imageFiles.value = []
      imagesToPdfResult.value = null
      outputPdfFilename.value = 'output.pdf'
    }

    const resetFolderToPdfForm = () => {
      folderQueue.value = []
      folderToPdfResult.value = null
      batchOutputFilename.value = 'combined.pdf'
    }

    const resetMergePdfsForm = () => {
      mergePdfFiles.value = []
      mergePdfsResult.value = null
      mergeOutputFilename.value = 'merged.pdf'
    }

    return {
      conversionMode,
      // PDF to Images
      pdfFile,
      pdfToImagesResult,
      pdfToImagesLoading,
      handlePdfFileChange,
      handlePdfToImages,
      resetPdfToImagesForm,
      // Images to PDF
      imageFiles,
      imagesToPdfResult,
      imagesToPdfLoading,
      outputPdfFilename,
      handleImageFilesChange,
      handleImageFileRemove,
      handleImagesToPdf,
      resetImagesToPdfForm,
      // Folder to PDF - Batch Queue
      folderQueue,
      totalFoldersInQueue,
      totalFilesInQueue,
      folderToPdfResult,
      folderToPdfLoading,
      batchOutputFilename,
      isDraggingOver,
      handleAddFolder,
      handleDragOver,
      handleDragLeave,
      handleDrop,
      removeFolderFromQueue,
      moveFolderUp,
      moveFolderDown,
      clearFolderQueue,
      handleBatchFoldersToPdf,
      resetFolderToPdfForm,
      // Merge PDFs
      mergePdfFiles,
      mergePdfsResult,
      mergePdfsLoading,
      mergeOutputFilename,
      handleMergePdfFilesChange,
      handleMergePdfFileRemove,
      handleMergePdfs,
      resetMergePdfsForm,
      // Common
      downloadFile,
    }
  },
})
