
import {getRequest, postRequest, deleteRequest} from './http'
import axios from 'axios'
import {BACKEND_BASE_URL} from '../config/constants'
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
    console.log('[PhotoClassifierService] postMoveFolder - Sending request:', payload)
    const responseData = await postRequest(PHOTO_CLASSIFIER_ENDPOINT_FOLDER, {}, payload)
    console.log('[PhotoClassifierService] postMoveFolder - Response:', responseData)
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
    try {
        const rootPath = getRootPath()
        const params = rootPath ? { rootPath } : {}
        // Use custom axios config to treat 404 as success (working state doesn't exist yet)
        const res = await axios.get(BACKEND_BASE_URL + '/photo-classifier/working-state', {
            params,
            validateStatus: (status) => status === 200 || status === 404
        })

        if (res.status === 404) {
            console.log('[Service] Working state not found (404) - this is expected for new directories')
            return null
        }

        return res.data as WorkingState
    } catch (error: any) {
        // Handle other errors
        console.error('[Service] Failed to load working state:', error)
        throw error
    }
}

export async function clearWorkingState(targetRootPath?: string): Promise<void> {
    const rootPath = targetRootPath || getRootPath()
    const params = rootPath ? { rootPath } : {}
    await deleteRequest('/photo-classifier/working-state', params)
}
