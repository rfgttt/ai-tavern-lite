let sessionListRequestId = 0
let sessionLoadRequestId = 0

export const beginSessionListRequest = () => ++sessionListRequestId
export const isCurrentSessionListRequest = (requestId: number) => requestId === sessionListRequestId
export const invalidateSessionListRequests = () => { sessionListRequestId += 1 }

export const getSessionLoadRequestId = () => sessionLoadRequestId
export const invalidateSessionLoadRequests = () => { sessionLoadRequestId += 1 }
export const isCurrentSessionLoadRequest = (requestId: number) => requestId === sessionLoadRequestId

export const resetRequestGuards = () => {
  sessionListRequestId += 1
  sessionLoadRequestId += 1
}
