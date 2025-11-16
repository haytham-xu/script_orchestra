

import {getRequest, postRequest} from '@/basic/RequestService'
import {MANGA_CLASSIFIER_ENDPOINT_CONFIG, MANGA_CLASSIFIER_ENDPOINT_FOLDER} from '@/basic/Constants.ts'
import type {ButtonConfigJSON, FolderObjectList, FileList} from '@/manga_classifier/service/Model'
import { ElMessage } from 'element-plus'

export async function getButtonConfigJSON(): Promise<ButtonConfigJSON> {
    const responseData = await getRequest<ButtonConfigJSON>(MANGA_CLASSIFIER_ENDPOINT_CONFIG)
    return responseData
}

export async function getFolderList():Promise<FolderObjectList> {
    const responseData = await getRequest<FolderObjectList>(MANGA_CLASSIFIER_ENDPOINT_FOLDER)
    return responseData
}

export async function getFileList(folderName:string):Promise<FileList> {
    const responseData = await getRequest<FileList>(MANGA_CLASSIFIER_ENDPOINT_FOLDER + "/" + folderName)
    return responseData
}

export async function postMoveFolder(sourceFolderPath:string, targetFolderPath:string) {
    const payload = {
        "sourceFolderPath": sourceFolderPath,
        "targetFolderPath": targetFolderPath
    }
    const responseData = await postRequest(MANGA_CLASSIFIER_ENDPOINT_FOLDER, {}, payload)
    ElMessage.success(`Move success: ${sourceFolderPath}`)
    return responseData
}
