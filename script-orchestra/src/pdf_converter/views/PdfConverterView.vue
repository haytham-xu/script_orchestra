<template>
  <el-container class="pdf-converter-container">
    <el-header>
      <el-button @click="goBack" circle size="small"><el-icon><ArrowLeft /></el-icon></el-button>
      <h1>PDF Converter</h1>
    </el-header>

    <el-main>
      <!-- Mode Selection -->
      <el-radio-group v-model="conversionMode" size="large" class="mode-selector">
        <el-radio-button label="folder-to-pdf">Folder → PDF</el-radio-button>
        <el-radio-button label="images-to-pdf">Images → PDF</el-radio-button>
        <el-radio-button label="merge-pdfs">Merge PDFs</el-radio-button>
        <el-radio-button label="pdf-to-images">PDF → Images</el-radio-button>
      </el-radio-group>

      <el-divider />

      <!-- Folder to PDF Mode - Batch Queue (First/Default) -->
      <div v-if="conversionMode === 'folder-to-pdf'" class="conversion-panel">
        <h2>Convert Folders to PDF (Batch Mode)</h2>
        <p class="description">
          Drag folders directly here or click the button to add folders to queue. All images from all folders (including subfolders) will be merged into a single PDF, sorted naturally.
        </p>

        <!-- Drag and Drop Zone -->
        <div
          class="folder-drop-zone"
          :class="{ 'drag-over': isDraggingOver }"
          @drop="handleDrop"
          @dragover="handleDragOver"
          @dragleave="handleDragLeave"
          @dragenter.prevent
        >
          <el-icon :size="64" class="drop-icon"><upload-filled /></el-icon>
          <p class="drop-text">Drag folders here</p>
          <el-divider>OR</el-divider>
          <input
            type="file"
            webkitdirectory
            directory
            multiple
            @change="handleAddFolder"
            ref="folderInputRef"
            style="display: none"
            id="folder-input"
          />
          <el-button type="success" size="large" @click="triggerFolderInput">
            <el-icon><circle-plus /></el-icon>
            Browse & Select Folder
          </el-button>
        </div>

        <!-- Folder Queue Display -->
        <div v-if="folderQueue.length > 0" class="folder-queue">
          <el-card class="queue-summary" shadow="never">
            <div class="queue-header">
              <h3>📁 Folder Queue ({{ totalFoldersInQueue }} folders, {{ totalFilesInQueue }} files)</h3>
              <el-button type="danger" size="small" @click="clearFolderQueue" plain>
                Clear All
              </el-button>
            </div>
          </el-card>

          <el-card
            v-for="(folder, index) in folderQueue"
            :key="folder.id"
            class="queue-item"
            shadow="hover"
          >
            <div class="queue-item-content">
              <div class="folder-icon">
                <el-icon size="32" color="#409EFF"><folder /></el-icon>
              </div>
              <div class="folder-details">
                <p class="folder-name">{{ folder.name }}</p>
                <p class="folder-file-count">{{ folder.fileCount }} files</p>
              </div>
              <div class="folder-actions">
                <el-button-group>
                  <el-button
                    size="small"
                    @click="moveFolderUp(index)"
                    :disabled="index === 0"
                    title="Move up"
                  >
                    <el-icon><top /></el-icon>
                  </el-button>
                  <el-button
                    size="small"
                    @click="moveFolderDown(index)"
                    :disabled="index === folderQueue.length - 1"
                    title="Move down"
                  >
                    <el-icon><bottom /></el-icon>
                  </el-button>
                </el-button-group>
                <el-button
                  type="danger"
                  size="small"
                  @click="removeFolderFromQueue(folder.id)"
                  circle
                  style="margin-left: 10px"
                >
                  <el-icon><delete /></el-icon>
                </el-button>
              </div>
            </div>
          </el-card>

          <div class="batch-actions">
            <div class="filename-input">
              <el-input
                v-model="batchOutputFilename"
                placeholder="Enter output PDF filename"
                size="large"
              >
                <template #prepend>Output Filename:</template>
              </el-input>
            </div>

            <el-button
              type="primary"
              size="large"
              @click="handleBatchFoldersToPdf"
              :loading="folderToPdfLoading"
              class="convert-button"
            >
              <el-icon><magic-stick /></el-icon>
              <span>Convert All to PDF ({{ totalFoldersInQueue }} folders)</span>
            </el-button>
          </div>
        </div>

        <div v-else class="empty-queue">
          <el-empty description="No folders in queue. Click 'Add Folder to Queue' to start." />
        </div>

        <!-- Results -->
        <div v-if="folderToPdfResult" class="results-section">
          <h3>PDF Created Successfully!</h3>
          <p class="success-info">Combined {{ totalFoldersInQueue }} folders into one PDF</p>

          <el-card class="pdf-result-card" shadow="hover">
            <div class="pdf-info">
              <el-icon size="48" color="#409EFF"><document /></el-icon>
              <div class="pdf-details">
                <p class="filename">{{ folderToPdfResult.filename }}</p>
                <el-button
                  type="primary"
                  size="large"
                  @click="downloadFile(folderToPdfResult.pdfUrl)"
                >
                  <el-icon><download /></el-icon>
                  Download PDF
                </el-button>
              </div>
            </div>
          </el-card>

          <el-button size="large" @click="resetFolderToPdfForm" class="reset-button">
            Reset & Clear Queue
          </el-button>
        </div>
      </div>

      <!-- Images to PDF Mode -->
      <div v-else-if="conversionMode === 'images-to-pdf'" class="conversion-panel">
        <h2>Convert Images to PDF</h2>

        <el-upload
          class="upload-area"
          drag
          :auto-upload="false"
          :on-change="handleImageFilesChange"
          :on-remove="handleImageFileRemove"
          multiple
          accept=".png,.jpg,.jpeg,.bmp,.gif,.tiff"
          :show-file-list="true"
          list-type="picture"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            Drop image files here or <em>click to upload</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              Supports: PNG, JPG, JPEG, BMP, GIF, TIFF (multiple files)
            </div>
          </template>
        </el-upload>

        <div class="filename-input">
          <el-input
            v-model="outputPdfFilename"
            placeholder="Enter output PDF filename"
            size="large"
          >
            <template #prepend>Output Filename:</template>
          </el-input>
        </div>

        <el-button
          type="primary"
          size="large"
          @click="handleImagesToPdf"
          :loading="imagesToPdfLoading"
          :disabled="imageFiles.length === 0"
          class="convert-button"
        >
          <el-icon><magic-stick /></el-icon>
          <span>Convert to PDF</span>
        </el-button>

        <!-- Results -->
        <div v-if="imagesToPdfResult" class="results-section">
          <h3>PDF Created Successfully!</h3>

          <el-card class="pdf-result-card" shadow="hover">
            <div class="pdf-info">
              <el-icon size="48" color="#409EFF"><document /></el-icon>
              <div class="pdf-details">
                <p class="filename">{{ imagesToPdfResult.filename }}</p>
                <el-button
                  type="primary"
                  size="large"
                  @click="downloadFile(imagesToPdfResult.pdfUrl)"
                >
                  <el-icon><download /></el-icon>
                  Download PDF
                </el-button>
              </div>
            </div>
          </el-card>

          <el-button size="large" @click="resetImagesToPdfForm" class="reset-button">
            Reset
          </el-button>
        </div>
      </div>

      <!-- Merge PDFs Mode -->
      <div v-else-if="conversionMode === 'merge-pdfs'" class="conversion-panel">
        <h2>Merge PDFs</h2>
        <p class="description">
          Select multiple PDF files to merge them into a single PDF document.
        </p>

        <el-upload
          class="upload-area"
          drag
          :auto-upload="false"
          :on-change="handleMergePdfFilesChange"
          :on-remove="handleMergePdfFileRemove"
          multiple
          accept=".pdf"
          :show-file-list="true"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            Drop PDF files here or <em>click to upload</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              PDF files only (Select at least 2 files)
            </div>
          </template>
        </el-upload>

        <div v-if="mergePdfFiles.length > 0" class="merge-info">
          <el-alert
            :title="`${mergePdfFiles.length} PDF files selected`"
            type="info"
            :closable="false"
          />

          <div class="filename-input">
            <el-input
              v-model="mergeOutputFilename"
              placeholder="Enter output PDF filename"
              size="large"
            >
              <template #prepend>Output Filename:</template>
            </el-input>
          </div>

          <el-button
            type="primary"
            size="large"
            @click="handleMergePdfs"
            :loading="mergePdfsLoading"
            :disabled="mergePdfFiles.length < 2"
            class="convert-button"
          >
            <el-icon><connection /></el-icon>
            <span>Merge PDFs</span>
          </el-button>
        </div>

        <!-- Results -->
        <div v-if="mergePdfsResult" class="results-section">
          <h3>PDFs Merged Successfully!</h3>
          <p class="merge-count">{{ mergePdfsResult.mergedCount }} files merged</p>

          <el-card class="pdf-result-card" shadow="hover">
            <div class="pdf-info">
              <el-icon size="48" color="#409EFF"><document /></el-icon>
              <div class="pdf-details">
                <p class="filename">{{ mergePdfsResult.filename }}</p>
                <el-button
                  type="primary"
                  size="large"
                  @click="downloadFile(mergePdfsResult.pdfUrl)"
                >
                  <el-icon><download /></el-icon>
                  Download Merged PDF
                </el-button>
              </div>
            </div>
          </el-card>

          <el-button size="large" @click="resetMergePdfsForm" class="reset-button">
            Reset
          </el-button>
        </div>
      </div>

      <!-- PDF to Images Mode -->
      <div v-else class="conversion-panel">
        <h2>Convert PDF to Images</h2>

        <el-upload
          class="upload-area"
          drag
          :auto-upload="false"
          :on-change="handlePdfFileChange"
          :limit="1"
          accept=".pdf"
          :show-file-list="true"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            Drop PDF file here or <em>click to upload</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">PDF files only</div>
          </template>
        </el-upload>

        <el-button
          type="primary"
          size="large"
          @click="handlePdfToImages"
          :loading="pdfToImagesLoading"
          :disabled="!pdfFile"
          class="convert-button"
        >
          <el-icon><magic-stick /></el-icon>
          <span>Convert to Images</span>
        </el-button>

        <!-- Results -->
        <div v-if="pdfToImagesResult" class="results-section">
          <h3>Conversion Results ({{ pdfToImagesResult.count }} pages)</h3>

          <div class="images-grid">
            <el-card
              v-for="(imageUrl, index) in pdfToImagesResult.images"
              :key="index"
              class="image-card"
              shadow="hover"
            >
              <img :src="imageUrl" :alt="`Page ${index + 1}`" class="preview-image" />
              <div class="image-actions">
                <span>Page {{ index + 1 }}</span>
                <el-button type="primary" size="small" @click="downloadFile(imageUrl)">
                  <el-icon><download /></el-icon>
                  Download
                </el-button>
              </div>
            </el-card>
          </div>

          <el-button
            type="success"
            size="large"
            @click="downloadFile(pdfToImagesResult.zipUrl)"
            class="download-all-button"
          >
            <el-icon><folder-opened /></el-icon>
            <span>Download All (ZIP)</span>
          </el-button>

          <el-button size="large" @click="resetPdfToImagesForm" class="reset-button">
            Reset
          </el-button>
        </div>
      </div>
    </el-main>
  </el-container>
</template>

<script lang="ts" src="./PdfConverterView.ts"></script>

<style scoped>
.pdf-converter-container {
  min-height: 100vh;
  background-color: #f5f7fa;
}

.el-header {
  background-color: #fff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.el-header h1 {
  margin: 0;
  font-size: 24px;
  color: #303133;
}

.el-main {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.mode-selector {
  display: flex;
  justify-content: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.conversion-panel {
  background-color: #fff;
  border-radius: 8px;
  padding: 30px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.conversion-panel h2 {
  margin-top: 0;
  color: #303133;
  font-size: 20px;
}

.description {
  color: #606266;
  margin-bottom: 20px;
}

.upload-area {
  margin: 20px 0;
}

:deep(.el-upload-dragger) {
  padding: 40px;
}

.convert-button {
  width: 100%;
  margin-top: 20px;
}

.filename-input {
  margin: 20px 0;
}

/* Drag and Drop Zone */
.folder-drop-zone {
  margin: 20px 0;
  padding: 60px 40px;
  text-align: center;
  border: 3px dashed #dcdfe6;
  border-radius: 8px;
  background-color: #fafafa;
  transition: all 0.3s;
  cursor: pointer;
}

.folder-drop-zone:hover {
  border-color: #409eff;
  background-color: #f0f9ff;
}

.folder-drop-zone.drag-over {
  border-color: #67c23a;
  background-color: #f0f9ff;
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(103, 194, 58, 0.3);
}

.drop-icon {
  color: #909399;
  margin-bottom: 10px;
}

.folder-drop-zone.drag-over .drop-icon {
  color: #67c23a;
}

.drop-text {
  font-size: 18px;
  color: #606266;
  margin: 10px 0;
  font-weight: 500;
}

.folder-info,
.merge-info {
  margin-top: 20px;
}

.results-section {
  margin-top: 40px;
  padding-top: 30px;
  border-top: 2px solid #dcdfe6;
}

.results-section h3 {
  color: #409eff;
  margin-bottom: 20px;
}

.merge-count {
  color: #67c23a;
  font-size: 16px;
  margin-bottom: 20px;
}

.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.image-card {
  text-align: center;
}

.preview-image {
  width: 100%;
  height: 200px;
  object-fit: contain;
  background-color: #f5f7fa;
}

.image-actions {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.download-all-button {
  width: 100%;
  margin-bottom: 10px;
}

.reset-button {
  width: 100%;
}

.pdf-result-card {
  margin-bottom: 20px;
}

.pdf-info {
  display: flex;
  align-items: center;
  gap: 20px;
}

.pdf-details {
  flex: 1;
}

.pdf-details .filename {
  font-size: 18px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 10px;
}

/* Folder Queue Styles */
.folder-queue {
  margin-top: 30px;
}

.queue-summary {
  margin-bottom: 20px;
  background-color: #f0f9ff;
  border-left: 4px solid #409eff;
}

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.queue-header h3 {
  margin: 0;
  color: #409eff;
  font-size: 16px;
}

.queue-item {
  margin-bottom: 12px;
  transition: all 0.3s;
}

.queue-item:hover {
  transform: translateX(5px);
}

.queue-item-content {
  display: flex;
  align-items: center;
  gap: 15px;
}

.folder-icon {
  flex-shrink: 0;
}

.folder-details {
  flex: 1;
}

.folder-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.folder-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.folder-file-count {
  margin: 5px 0 0 0;
  font-size: 14px;
  color: #909399;
}

.batch-actions {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 2px dashed #dcdfe6;
}

.empty-queue {
  margin: 40px 0;
}

.success-info {
  color: #67c23a;
  font-size: 16px;
  margin-bottom: 20px;
}
</style>
