type AuthConfiguration = {
  clientId: string
  authority: string
  scope: string
  userFlow?: string
}

type OpenIdConfiguration = {
  authorization_endpoint: string
  token_endpoint: string
  end_session_endpoint?: string
}

type CachedToken = { accessToken: string; expiresAt: number }

const tokenKey = 'carefolio:access-token'
const transactionKey = 'carefolio:oidc-transaction'
let redirectResult: Promise<string | null> | null = null

function configuration(): AuthConfiguration | null {
  const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID?.trim()
  const authority = import.meta.env.VITE_ENTRA_AUTHORITY?.trim().replace(/\/$/, '')
  const scope = import.meta.env.VITE_ENTRA_API_SCOPE?.trim()
  const userFlow = import.meta.env.VITE_ENTRA_USER_FLOW?.trim()
  return clientId && authority && scope ? { clientId, authority, scope, userFlow } : null
}

export function authEnabled(): boolean {
  return configuration() !== null
}

export function signupEnabled(): boolean {
  return Boolean(configuration()?.userFlow)
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

function randomValue(bytes = 32): string {
  const value = crypto.getRandomValues(new Uint8Array(bytes))
  return base64Url(value)
}

function base64Url(value: Uint8Array): string {
  let binary = ''
  for (const byte of value) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function discover(authority: string): Promise<OpenIdConfiguration> {
  const url = `${authority}/.well-known/openid-configuration`
  const response = await fetch(url)
  if (!response.ok) throw new Error('Could not load sign-in configuration for this Entra tenant.')
  return response.json() as Promise<OpenIdConfiguration>
}

async function beginAuthentication(): Promise<void> {
  const config = configuration()
  if (!config) throw new Error('Set the Entra client ID, authority, and API scope to enable sign-in.')
  const oidc = await discover(config.authority)
  const verifier = randomValue(48)
  const state = randomValue()
  const nonce = randomValue()
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  const challenge = base64Url(new Uint8Array(digest))
  sessionStorage.setItem(transactionKey, JSON.stringify({ verifier, state, nonce }))

  const url = new URL(oidc.authorization_endpoint)
  const authorizationParams: Record<string, string> = {
    client_id: config.clientId,
    response_type: 'code',
    redirect_uri: import.meta.env.VITE_ENTRA_REDIRECT_URI || window.location.origin,
    response_mode: 'query',
    scope: `openid profile ${config.scope}`,
    state,
    nonce,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  }
  if (config.userFlow) authorizationParams.p = config.userFlow
  url.search = new URLSearchParams(authorizationParams).toString()
  window.location.assign(url.toString())
}

export async function beginSignIn(): Promise<void> {
  return beginAuthentication()
}

export async function beginSignUp(): Promise<void> {
  const config = configuration()
  if (!config?.userFlow) {
    throw new Error('Set VITE_ENTRA_USER_FLOW to enable account creation.')
  }
  return beginAuthentication()
}

function jwtPayload(token: string): Record<string, unknown> {
  const part = token.split('.')[1]
  if (!part) throw new Error('Sign-in response did not contain a valid identity token.')
  const normalized = part.replace(/-/g, '+').replace(/_/g, '/')
  return JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '='))) as Record<string, unknown>
}

export function completeSignIn(): Promise<string | null> {
  if (!redirectResult) redirectResult = completeSignInOnce()
  return redirectResult
}

async function completeSignInOnce(): Promise<string | null> {
  const params = new URLSearchParams(window.location.search)
  if (params.has('error')) {
    const description = params.get('error_description')
    window.history.replaceState({}, document.title, window.location.pathname)
    sessionStorage.removeItem(transactionKey)
    throw new Error(description || 'Entra sign-in was not completed.')
  }
  const code = params.get('code')
  if (!code) return currentAccessToken()

  const config = configuration()
  const transaction = sessionStorage.getItem(transactionKey)
  sessionStorage.removeItem(transactionKey)
  window.history.replaceState({}, document.title, window.location.pathname)
  if (!config || !transaction) throw new Error('Sign-in expired. Please try again.')
  const callbackState = params.get('state')
  const { verifier, state, nonce } = JSON.parse(transaction) as { verifier: string; state: string; nonce: string }
  if (!callbackState || callbackState !== state) throw new Error('Sign-in state did not match. Please try again.')

  const oidc = await discover(config.authority)
  const response = await fetch(oidc.token_endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: config.clientId,
      grant_type: 'authorization_code',
      code,
      redirect_uri: import.meta.env.VITE_ENTRA_REDIRECT_URI || window.location.origin,
      code_verifier: verifier,
      scope: `openid profile ${config.scope}`,
    }),
  })
  if (!response.ok) throw new Error('Entra could not exchange the sign-in code. Check the app registration settings.')
  const result = await response.json() as { access_token?: string; id_token?: string; expires_in?: number }
  if (!result.access_token || !result.id_token || !result.expires_in) throw new Error('Entra returned an incomplete sign-in response.')
  const idClaims = jwtPayload(result.id_token)
  if (idClaims.nonce !== nonce) throw new Error('Sign-in nonce did not match. Please try again.')
  sessionStorage.setItem(tokenKey, JSON.stringify({
    accessToken: result.access_token,
    expiresAt: Date.now() + result.expires_in * 1000,
  } satisfies CachedToken))
  return result.access_token
}

export async function signOut(): Promise<void> {
  sessionStorage.removeItem(tokenKey)
  sessionStorage.removeItem(transactionKey)
  const config = configuration()
  if (!config) return
  try {
    const oidc = await discover(config.authority)
    if (!oidc.end_session_endpoint) return
    const url = new URL(oidc.end_session_endpoint)
    url.search = new URLSearchParams({
      client_id: config.clientId,
      post_logout_redirect_uri: import.meta.env.VITE_ENTRA_REDIRECT_URI || window.location.origin,
    }).toString()
    window.location.assign(url.toString())
  } catch {
    // The local access-token cache has already been cleared; a tenant logout
    // endpoint failure should not restore a signed-in application session.
  }
}
