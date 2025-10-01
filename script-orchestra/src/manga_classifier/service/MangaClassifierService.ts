
import {getRequest, postRequest} from '@/manga_classifier/service/RequestService.ts'
import type {ButtonConfigJSON, FolderObjectList, FileList} from '@/manga_classifier/model/Model'
import {ENDPOINT_CONFIG, ENDPOINT_FOLDER} from '@/manga_classifier/constants/index.ts'
import { ElMessage } from 'element-plus'

export async function getButtonConfigJSON(): Promise<ButtonConfigJSON> {
    const responseData = await getRequest<ButtonConfigJSON>(ENDPOINT_CONFIG)
    return responseData
}

export async function getFolderList():Promise<FolderObjectList> {
    const responseData = await getRequest<FolderObjectList>(ENDPOINT_FOLDER)
    return responseData
}

export async function getFileList(folderName:string):Promise<FileList> {
    const responseData = await getRequest<FileList>(ENDPOINT_FOLDER + "/" + folderName)
    return responseData
}

export async function postMoveFolder(sourceFolderPath:string, targetFolderPath:string) {
    const payload = {
        "sourceFolderPath": sourceFolderPath,
        "targetFolderPath": targetFolderPath
    }
    const responseData = await postRequest(ENDPOINT_FOLDER, {}, payload)
    ElMessage.success(`Move success: ${sourceFolderPath}`)
    return responseData
}
