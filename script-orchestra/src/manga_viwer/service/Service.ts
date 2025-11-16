import {getRequest, putRequest} from '@/basic/RequestService'
import {MANGA_VIEWER_INDEX_ENDPOINT, MANGA_VIEWER_FOLDER_SCAN_ENDPINT, MANGA_VIEWER_UPDATE_ENDPOINT, MANGA_VIEWER_HOTTAG_ENDPOINT} from '@/basic/Constants.ts'
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

export async function fetchHotTags(): Promise<string[]> {
  return await getRequest<string[]>(MANGA_VIEWER_HOTTAG_ENDPOINT)
}

// export async function updateFolder(folderId: string, payload: UpdateFolderPayload): Promise<FolderModel | null> {
//   try {
//     const r = await axios.put(`${BASE}${UPDATE_ENDPOINT}/${folderId}`, payload)
//     ElMessage.success('Updated')
//     return r.data as FolderModel
//   } catch (e: any) {
//     ElMessage.error(e?.message || 'Update failed')
//     return null
//   }
// }

// Utility: parse filename blocks for advanced tag assist
// Example: [auth1]aaa｜aa[useless](ul_tag1)【ul_tag2】 => blocks: [auth1], aaa, aa, [useless], (ul_tag1), 【ul_tag2】
// export function splitFilenameBlocks(name: string): string[] {
//   // Replace full-width vertical bar ｜ or ASCII | with a uniform delimiter
//   const normalized = name.replace(/[\|｜]+/g, '§')
//   // Regex capturing bracketed / parenthesis chunks
//   const pattern = /(\[[^\]]+\])|(\([^)]+\))|(【[^】]+】)|([^§\[\(\]【】]+)/g
//   const raw = normalized.match(pattern) || []
//   const blocks = raw.map(s => s.trim()).filter(Boolean)
//   return blocks
// }
