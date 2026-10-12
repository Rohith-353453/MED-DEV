import { currentAccessToken } from './auth'
import type { ApiDocument, DocumentKind, DocumentListItem, ExtractedData, Page, Profile, Summary, TimelineEvent } from '../types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = currentAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  if (response.status === 204) return undefined as T
  const contentType = response.headers.get('content-type') ?? ''
  const result = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const message = typeof result === 'object' && result && 'detail' in result
      ? String((result as { detail: unknown }).detail)
      : typeof result === 'string' && result ? result : `Request failed (${response.status})`
    if (response.status === 401) throw new Error('Sign-in is required or has expired. Please sign in again.')
    throw new Error(message)
  }
  return result as T
}

export const api = {
  listDocuments: () => request<Page<DocumentListItem>>('/documents?limit=100'),
  getDocument: (id: string) => request<ApiDocument>(`/documents/${encodeURIComponent(id)}`),
  upload: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<{ document_id: string; status: string }>('/documents', { method: 'POST', body })
  },
  updateDocument: (id: string, changes: { display_name?: string; document_type?: DocumentKind | null; document_date?: string | null; extracted_data?: ExtractedData }) =>
    request<ApiDocument>(`/documents/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  reprocess: (id: string) => request<{ document_id: string; status: string }>(`/documents/${encodeURIComponent(id)}/reprocess`, { method: 'POST' }),
  resetExtraction: (id: string) => request<ApiDocument>(`/documents/${encodeURIComponent(id)}/extraction-overrides`, { method: 'DELETE' }),
  deleteDocument: (id: string) => request<void>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  generateSummary: (id: string, language: string) => request<Summary>(`/documents/${encodeURIComponent(id)}/summaries`, { method: 'POST', body: JSON.stringify({ language }) }),
  updateSummary: (documentId: string, summaryId: string, summary_text: string, language: string) =>
    request<Summary>(`/documents/${encodeURIComponent(documentId)}/summary/${encodeURIComponent(summaryId)}`, { method: 'PATCH', body: JSON.stringify({ summary_text, language }) }),
  getTimeline: () => request<Page<TimelineEvent>>('/timeline?limit=100'),
  updateEvent: (id: string, changes: Partial<Pick<TimelineEvent, 'event_date' | 'event_type' | 'title' | 'description' | 'data'>>) =>
    request<TimelineEvent>(`/timeline/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  deleteEvent: (id: string) => request<void>(`/timeline/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  getProfile: () => request<Profile>('/profile/me'),
  updateProfile: (changes: Partial<Pick<Profile, 'display_name' | 'preferred_language' | 'birth_date' | 'gender'>>) =>
    request<Profile>('/profile/me', { method: 'PATCH', body: JSON.stringify(changes) }),
  download: async (id: string): Promise<Blob> => {
    const headers = new Headers()
    const token = currentAccessToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(`${API_BASE_URL}/documents/${encodeURIComponent(id)}/content`, { headers })
    if (!response.ok) throw new Error(response.status === 401 ? 'Sign-in is required or has expired.' : 'Could not open this document.')
    return response.blob()
  },
}

export function documentKindLabel(kind: DocumentKind | null | undefined): string {
  return (kind || 'other').replace(/_/g, ' ').replace(/\b\w/g, (letter: string) => letter.toUpperCase())
}

export function documentStatusLabel(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (letter: string) => letter.toUpperCase())
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return 'Date not recorded'
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(parsed)
}
