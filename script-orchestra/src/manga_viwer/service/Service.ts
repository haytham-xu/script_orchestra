import {getRequest, putRequest} from '@/basic/RequestService'
import {MANGA_VIEWER_INDEX_ENDPOINT, MANGA_VIEWER_FOLDER_SCAN_ENDPINT, MANGA_VIEWER_UPDATE_ENDPOINT} from '@/basic/Constants.ts'
import type { MangaIndex, FolderModel } from '@/manga_viwer/service/Model'

export async function fetchIndex(): Promise<MangaIndex> {
  return await getRequest<MangaIndex>(MANGA_VIEWER_INDEX_ENDPOINT)
}

export async function fetchFileList(folderId:string): Promise<string[]> {
  return await getRequest<string[]>(MANGA_VIEWER_FOLDER_SCAN_ENDPINT, { folderId: folderId })
}

export async function updateFolderModels(folderModels:Record<string, FolderModel>, classifierMode: boolean): Promise<void> {
  await putRequest<FolderModel>(MANGA_VIEWER_UPDATE_ENDPOINT + "/" + classifierMode, {}, folderModels)
}

