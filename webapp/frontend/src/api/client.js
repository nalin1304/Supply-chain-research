/**
 * API client for the Supply Chain AI backend.
 * All API calls go through this module.
 */

const BASE_URL = '/api'

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`

  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  }

  const response = await fetch(url, config)

  if (!response.ok) {
    const error = new Error(`API Error: ${response.status} ${response.statusText}`)
    error.status = response.status
    throw error
  }

  return response.json()
}

// Dashboard
export function fetchSummary() {
  return request('/dashboard/summary')
}

export function fetchNetworkNodes() {
  return request('/dashboard/network-nodes')
}

// Optimization
export function fetchParetoFront() {
  return request('/optimization/pareto-front')
}

export function fetchHypervolume() {
  return request('/optimization/hypervolume')
}

export function runScenario(params) {
  return request('/optimization/run-scenario', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

// Simulation
export function fetchServiceLevel() {
  return request('/simulation/service-level')
}

export function fetchResilienceMetrics() {
  return request('/simulation/resilience-metrics')
}

export function runShock(params) {
  return request('/simulation/run-shock', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

// Forecasting
export function fetchForecast() {
  return request('/forecasting/forecast')
}

export function fetchAttentionWeights() {
  return request('/forecasting/attention-weights')
}

// Health
export function fetchHealth() {
  return request('/health')
}
