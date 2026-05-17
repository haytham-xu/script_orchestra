
import {getRequest, postRequest, deleteRequest} from './http'
import type {DefaultGroup, GroupList} from '@/photo_classifier/service/Model'
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

// Working State APIs
export interface WorkingState {
    rootPath: string
    timestamp: string
    defaultGroup: DefaultGroup
    groupList: GroupList
}

export async function saveWorkingState(state: Omit<WorkingState, 'rootPath' | 'timestamp'>): Promise<void> {
    const rootPath = getRootPath()
    const payload = {
        rootPath,
        timestamp: new Date().toISOString(),
        ...state
    }
    await postRequest('/photo-classifier/working-state', {}, payload)
}

export async function loadWorkingState(): Promise<WorkingState | null> {
    const rootPath = getRootPath()
    const params = rootPath ? { rootPath } : {}
    const responseData = await getRequest<WorkingState | null>('/photo-classifier/working-state', params)
    return responseData
}

export async function clearWorkingState(targetRootPath?: string): Promise<void> {
    const rootPath = targetRootPath || getRootPath()
    const params = rootPath ? { rootPath } : {}
    await deleteRequest('/photo-classifier/working-state', params)
}
