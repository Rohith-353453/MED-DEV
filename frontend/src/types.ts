export type DocumentStatus = 'queued' | 'processing' | 'completed' | 'needs_review' | 'failed'
export type DocumentKind = 'prescription' | 'lab_report' | 'discharge_summary' | 'diagnostic' | 'other'
export type LabFlag = 'H' | 'L' | 'N' | 'HH' | 'LL'

export interface PatientInfo {
  name: string | null
  age: string | null
  gender: string | null
  confidence: number
  source_page?: number | null
}

export interface Medication {
  name: string
  dosage: string | null
  frequency: string | null
  duration: string | null
  route: string | null
  instructions: string | null
  confidence: number
  source_page?: number | null
}

export interface LabResult {
  test_name: string
  value: string | null
  unit: string | null
  reference_range: string | null
  flag: LabFlag | null
  date: string | null
  confidence: number
  source_page?: number | null
}

export interface Diagnosis {
  name: string
  date: string | null
  confidence: number
  source_page?: number | null
}

export interface ExtractedData {
  document_type: DocumentKind
  patient_info: PatientInfo | null
  medications: Medication[]
  lab_results: LabResult[]
  diagnoses: Diagnosis[]
  document_date: string | null
  notes: string | null
  overall_confidence: number
}

export interface Summary {
  id: string
  document_id: string
  language: string
  summary_text: string
  prompt_version: string
  model_name: string
  is_user_edited: boolean
  created_at: string
  updated_at: string
}

export interface ApiDocument {
  id: string
  display_name: string
  mime_type: string
  size_bytes: number
  page_count: number | null
  pages_processed: number
  pages_omitted: number
  document_type: DocumentKind | null
  document_date: string | null
  status: DocumentStatus
  extracted_data: ExtractedData
  summaries: Summary[]
  processing_error: string | null
  created_at: string
  updated_at: string
}

export interface DocumentListItem {
  id: string
  display_name: string
  mime_type: string
  size_bytes: number
  document_type: DocumentKind | null
  document_date: string | null
  status: DocumentStatus
  created_at: string
  updated_at: string
}

export interface TimelineEvent {
  id: string
  document_id: string | null
  event_type: string
  event_date: string | null
  title: string
  description: string | null
  data: Record<string, unknown>
  is_user_edited: boolean
  created_at: string
  updated_at: string
}

export interface Profile {
  id: string
  display_name: string | null
  preferred_language: string
  birth_date: string | null
  gender: string | null
  created_at: string
  updated_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
