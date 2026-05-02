
import {getRequest, postRequest} from './http'
import type {DefaultGroup} from '@/photo_classifier/service/Model'
import {PHOTO_CLASSIFIER_ENDPOINT_FOLDER} from '../config/constants'
import {getRootPath} from '../config/settings'

export async function getFileList():Promise<DefaultGroup> {
    const rootPath = getRootPath()
    const params = rootPath ? { rootPath } : {}
    const responseData = await getRequest<DefaultGroup>(PHOTO_CLASSIFIER_ENDPOINT_FOLDER, params)
    return responseData
}

export async function postMoveFolder(sourceFolderPath:string, targetFolderPath:string) {
    const rootPath = getRootPath()
    const payload = {
        "sourceFolderPath": sourceFolderPath,
        "targetFolderPath": targetFolderPath,
        "rootPath": rootPath
    }
    const responseData = await postRequest(PHOTO_CLASSIFIER_ENDPOINT_FOLDER, {}, payload)
    return responseData
}
