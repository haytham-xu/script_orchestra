import {getRequest, putRequest, deleteRequest} from '@/basic/RequestService'
import {MANGA_VIEWER_INDEX_ENDPOINT, MANGA_VIEWER_FOLDER_SCAN_ENDPINT, MANGA_VIEWER_UPDATE_ENDPOINT, MANGA_VIEWER_HOTTAG_ENDPOINT, MANGA_VIEWER_DELETE_ENDPOINT} from '@/basic/Constants.ts'
import type { MangaIndex, FolderModel } from '@/manga_viwer/service/Model'

export async function fetchIndex(): Promise<MangaIndex> {
  return await getRequest<MangaIndex>(MANGA_VIEWER_INDEX_ENDPOINT)
}

export async function fetchFileList(folderId:string): Promise<string[]> {
  return await getRequest<string[]>(MANGA_VIEWER_FOLDER_SCAN_ENDPINT, { folderId: folderId })
}

export async function updateFolderModel(folderModel:FolderModel): Promise<FolderModel | null> {
  return await putRequest<FolderModel>(MANGA_VIEWER_UPDATE_ENDPOINT + folderModel.id, {}, folderModel)
}

export async function deleteFolderModel(folderModel:FolderModel): Promise<FolderModel | null> {
  return await deleteRequest<FolderModel>(MANGA_VIEWER_DELETE_ENDPOINT + folderModel.id, {})
}

export async function fetchHotTags(): Promise<string[]> {
  return await getRequest<string[]>(MANGA_VIEWER_HOTTAG_ENDPOINT)
}
