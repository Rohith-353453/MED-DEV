import { initializeApp, getApps } from 'firebase/app'
import {
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  type User,
} from 'firebase/auth'

type CachedToken = { accessToken: string; expiresAt: number }

const tokenKey = 'carefolio:access-token'
let authReady: Promise<User | null> | null = null

export function authErrorMessage(error: unknown, fallback: string): string {
  const code = typeof error === 'object' && error && 'code' in error
    ? String((error as { code: unknown }).code)
    : ''
  const messages: Record<string, string> = {
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/missing-password': 'Enter a password.',
    'auth/weak-password': 'Use a password with at least 6 characters.',
    'auth/email-already-in-use': 'That email already has an account. Choose Sign in instead.',
    'auth/invalid-credential': 'The email or password is incorrect.',
    'auth/user-not-found': 'The email or password is incorrect.',
    'auth/wrong-password': 'The email or password is incorrect.',
    'auth/too-many-requests': 'Too many attempts. Wait a moment and try again.',
    'auth/network-request-failed': 'Firebase could not be reached. Check your connection and try again.',
  }
  if (messages[code]) return messages[code]
  return error instanceof Error ? error.message : fallback
}

function firebaseConfig() {
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY?.trim()
  const authDomain = import.meta.env.VITE_FIREBASE_AUTH_DOMAIN?.trim()
  const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID?.trim()
  const appId = import.meta.env.VITE_FIREBASE_APP_ID?.trim()
  return apiKey && authDomain && projectId && appId ? { apiKey, authDomain, projectId, appId } : null
}

function firebaseAuth() {
  const config = firebaseConfig()
  if (!config) return null
  const app = getApps().find((candidate) => candidate.name === 'carefolio') ?? initializeApp(config, 'carefolio')
  return getAuth(app)
}

export function authEnabled(): boolean {
  return firebaseAuth() !== null
}

export function currentAccessToken(): string | null {
  const serialized = sessionStorage.getItem(tokenKey)
  if (!serialized) return null
  try {
    const token = JSON.parse(serialized) as CachedToken
    if (token.expiresAt <= Date.now() + 60_000) {
      sessionStorage.removeItem(tokenKey)
      return null
    }
    return token.accessToken
  } catch {
    sessionStorage.removeItem(tokenKey)
    return null
  }
}

function cacheUser(user: User | null): Promise<string | null> {
  if (!user) {
    sessionStorage.removeItem(tokenKey)
    return Promise.resolve(null)
  }
  return user.getIdToken().then((accessToken) => {
    const expiresAt = Date.now() + 55 * 60 * 1000
    sessionStorage.setItem(tokenKey, JSON.stringify({ accessToken, expiresAt } satisfies CachedToken))
    return accessToken
  })
}

async function cacheCurrentUser(auth: ReturnType<typeof getAuth>): Promise<string> {
  const user = auth.currentUser
  if (!user) throw new Error('Firebase sign-in completed without an active user session.')
  const accessToken = await cacheUser(user)
  if (!accessToken) throw new Error('Firebase sign-in did not return an access token.')
  return accessToken
}

export function completeSignIn(): Promise<string | null> {
  if (!authReady) {
    const auth = firebaseAuth()
    authReady = auth
      ? new Promise((resolve) => onAuthStateChanged(auth, (user) => void cacheUser(user).then(() => resolve(user))))
      : Promise.resolve(null)
  }
  return authReady.then((user) => user ? currentAccessToken() : null)
}

export async function beginSignIn(email: string, password: string): Promise<string> {
  const auth = firebaseAuth()
  if (!auth) throw new Error('Firebase authentication is not configured for this build.')
  if (!email.trim() || !password) throw new Error('Email and password are required.')
  await signInWithEmailAndPassword(auth, email, password)
  return cacheCurrentUser(auth)
}

export async function signUpEnabled(email: string, password: string): Promise<string> {
  const auth = firebaseAuth()
  if (!auth) throw new Error('Firebase authentication is not configured for this build.')
  if (!email.trim() || !password) throw new Error('Email and password are required.')
  await createUserWithEmailAndPassword(auth, email, password)
  return cacheCurrentUser(auth)
}

export async function signOut(): Promise<void> {
  sessionStorage.removeItem(tokenKey)
  authReady = null
  const auth = firebaseAuth()
  if (auth) await firebaseSignOut(auth)
}
