
import {getRequest, postRequest} from '@/photo_classifier/service/RequestService.ts'
import type {DefaultGroup} from '@/photo_classifier/model/Model'
import {ENDPOINT_FOLDER} from '@/photo_classifier/constants/index.ts'

export async function getFileList():Promise<DefaultGroup> {
    const responseData = await getRequest<DefaultGroup>(ENDPOINT_FOLDER)
    console.log('getFileList', responseData)
    return responseData
}

export async function postMoveFolder(sourceFolderPath:string, targetFolderPath:string) {
    const payload = {
        "sourceFolderPath": sourceFolderPath,
        "targetFolderPath": targetFolderPath
    }
    const responseData = await postRequest(ENDPOINT_FOLDER, {}, payload)
    return responseData
}
