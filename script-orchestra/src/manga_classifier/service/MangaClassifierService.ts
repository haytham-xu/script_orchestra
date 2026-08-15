

import {getRequest, postRequest} from '@/basic/RequestService'
import {MANGA_CLASSIFIER_ENDPOINT_CONFIG, MANGA_CLASSIFIER_ENDPOINT_FOLDER} from '@/basic/Constants.ts'
import type {ButtonConfigJSON, FolderObjectList, FileList} from '@/manga_classifier/service/Model'

export async function getButtonConfigJSON(): Promise<ButtonConfigJSON> {
    const responseData = await getRequest<ButtonConfigJSON>(MANGA_CLASSIFIER_ENDPOINT_CONFIG)
    return responseData
}

export async function getFolderList():Promise<FolderObjectList> {
    const responseData = await getRequest<FolderObjectList>(MANGA_CLASSIFIER_ENDPOINT_FOLDER)
    return responseData
}

export async function getFileList(folderName:string, signal?: AbortSignal):Promise<FileList> {
    const responseData = await getRequest<FileList>(MANGA_CLASSIFIER_ENDPOINT_FOLDER + "/" + folderName, {}, signal)
    return responseData
}

export async function postMoveFolder(sourceFolderPath:string, targetFolderPath:string) {
    const payload = {
        "sourceFolderPath": sourceFolderPath,
        "targetFolderPath": targetFolderPath
    }
    const responseData = await postRequest(MANGA_CLASSIFIER_ENDPOINT_FOLDER, {}, payload)
    return responseData
}

export async function postDeleteFolder(sourceFolderPath:string) {
    const payload = { "sourceFolderPath": sourceFolderPath }
    const responseData = await postRequest(MANGA_CLASSIFIER_ENDPOINT_FOLDER + "/delete", {}, payload)
    return responseData
}

export async function postUndo(sourceFolderPath: string) {
    const payload = { "sourceFolderPath": sourceFolderPath }
    const responseData = await postRequest(MANGA_CLASSIFIER_ENDPOINT_FOLDER + "/undo", {}, payload)
    return responseData as { message: string; restoredName: string }
}

export async function getUndoableSources(): Promise<string[]> {
    const responseData = await getRequest<{ sources: string[] }>(MANGA_CLASSIFIER_ENDPOINT_FOLDER + "/undoable")
    return responseData.sources
}
