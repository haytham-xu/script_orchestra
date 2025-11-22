
import {getRequest, postRequest} from '@/basic/RequestService.ts'
import type {DefaultGroup} from '@/photo_classifier/model/Model'
import {PHOTO_CLASSIFIER_ENDPOINT_FOLDER} from '@/basic/Constants'

export async function getFileList():Promise<DefaultGroup> {
    const responseData = await getRequest<DefaultGroup>(PHOTO_CLASSIFIER_ENDPOINT_FOLDER)
    return responseData
}

export async function postMoveFolder(sourceFolderPath:string, targetFolderPath:string) {
    const payload = {
        "sourceFolderPath": sourceFolderPath,
        "targetFolderPath": targetFolderPath
    }
    const responseData = await postRequest(PHOTO_CLASSIFIER_ENDPOINT_FOLDER, {}, payload)
    return responseData
}
