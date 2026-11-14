import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, Eye, EyeOff, Mail, Lock, User, CheckCircle } from 'lucide-react'
import { supabase, supabaseUrl } from '../supabase'
import ThreeBackground from '../components/ThreeBackground'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [showConfirmPass, setShowConfirmPass] = useState(false)
  const [isLogin, setIsLogin] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const formatAuthError = (err) => {
    const msg = err?.message || ''
    const isNetwork =
      msg.includes('Failed to fetch') ||
      msg.includes('fetch failed') ||
      err?.name === 'AuthRetryableFetchError'

    if (isNetwork) {
      return `Cannot reach Supabase Auth (${supabaseUrl}). Check your internet and verify this project URL in src/supabase.js and backend/.env.`
    }

    return msg || 'Authentication failed'
  }

  const handleRegister = async () => {
    setError('')
    setSuccess('')
    if (!name || !email || !password || !confirmPassword) {
      setError('Please fill in all fields!')
      return
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters!')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match!')
      return
    }
    setLoading(true)
    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: name } }
    })
    if (authError) {
      setError(formatAuthError(authError))
      setLoading(false)
      return
    }
    if (data.user) {
      const { error: profileError } = await supabase.from('profiles').insert([{
        id: data.user.id,
        name,
        email
      }])
      if (profileError) {
        setError(profileError.message)
        setLoading(false)
        return
      }
    }
    setLoading(false)
    setSuccess('Account created! Please login now.')
    setIsLogin(true)
    setEmail('')
    setPassword('')
    setName('')
    setConfirmPassword('')
  }

  const handleLogin = async () => {
    setError('')
    setSuccess('')
    if (!email || !password) {
      setError('Please enter your email and password!')
      return
    }
    setLoading(true)
    const { error: authError } = await supabase.auth.signInWithPassword({
      email,
      password
    })
    if (authError) {
      if (
        authError.name === 'AuthRetryableFetchError' ||
        (authError.message && (authError.message.includes('fetch failed') || authError.message.includes('Failed to fetch')))
      ) {
        setError(formatAuthError(authError))
      } else {
        setError('Invalid email or password!')
      }
      setLoading(false)
      return
    }
    setLoading(false)
    navigate('/dashboard')
  }

  const handleGoogleLogin = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/dashboard` }
    })
    if (error) setError(formatAuthError(error))
  }

  const switchTab = (toLogin) => {
    setIsLogin(toLogin)
    setError('')
    setSuccess('')
    setEmail('')
    setPassword('')
    setName('')
    setConfirmPassword('')
  }

  const inputStyle = {
    width: '100%', padding: '12px 14px 12px 42px',
    background: '#0a0e17', border: '1px solid #1e2d3d',
    borderRadius: '10px', color: '#fff', fontSize: '14px',
    outline: 'none', boxSizing: 'border-box',
  }

  const iconStyle = {
    position: 'absolute', left: '14px',
    top: '50%', transform: 'translateY(-50%)'
  }

  return (
    <div style={{
      minHeight: '100vh', background: '#0a0e17',
      display: 'flex', alignItems: 'center',
      justifyContent: 'center', padding: '20px', position: 'relative'
    }}>
      <ThreeBackground />      <div style={{
        position: 'fixed', top: '20%', left: '50%',
        transform: 'translateX(-50%)',
        width: '600px', height: '600px',
        background: 'radial-gradient(circle, rgba(0,212,255,0.05) 0%, transparent 70%)',
        pointerEvents: 'none'
      }} />

      <div style={{
        width: '100%', maxWidth: '420px',
        background: '#0d1117', border: '1px solid #1e2d3d',
        borderRadius: '20px', padding: '40px',
        position: 'relative', zIndex: 1
      }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div style={{
            width: '56px', height: '56px',
            background: 'linear-gradient(135deg, #00d4ff, #0066ff)',
            borderRadius: '16px', display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px'
          }}>
            <Activity size={28} color="white" />
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: '700', color: '#fff', marginBottom: '6px' }}>
            Trade-AI
          </h1>
          <p style={{ color: '#6b7a8d', fontSize: '14px' }}>
            {isLogin ? 'Welcome back! Sign in to continue' : 'Create your account to get started'}
          </p>
        </div>

        {/* Toggle */}
        <div style={{
          display: 'flex', background: '#0a0e17',
          borderRadius: '10px', padding: '4px',
          marginBottom: '24px', border: '1px solid #1e2d3d'
        }}>
          {['Login', 'Register'].map((tab) => (
            <button key={tab} onClick={() => switchTab(tab === 'Login')} style={{
              flex: 1, padding: '8px', borderRadius: '8px',
              border: 'none', cursor: 'pointer',
              fontSize: '14px', fontWeight: '500',
              background: (isLogin && tab === 'Login') || (!isLogin && tab === 'Register')
                ? 'linear-gradient(135deg, #00d4ff, #0066ff)' : 'transparent',
              color: (isLogin && tab === 'Login') || (!isLogin && tab === 'Register')
                ? '#fff' : '#6b7a8d',
            }}>{tab}</button>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            background: 'rgba(255,71,87,0.1)', border: '1px solid rgba(255,71,87,0.3)',
            borderRadius: '8px', padding: '10px 14px',
            color: '#ff4757', fontSize: '13px', marginBottom: '16px',
          }}>
            ⚠️ {error}
          </div>
        )}

        {/* Success */}
        {success && (
          <div style={{
            background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.3)',
            borderRadius: '8px', padding: '10px 14px',
            color: '#00ff88', fontSize: '13px', marginBottom: '16px',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}>
            <CheckCircle size={14} /> {success}
          </div>
        )}

        {/* Name (Register only) */}
        {!isLogin && (
          <div style={{ marginBottom: '16px' }}>
            <label style={{ fontSize: '13px', color: '#6b7a8d', marginBottom: '8px', display: 'block' }}>Full Name</label>
            <div style={{ position: 'relative' }}>
              <User size={16} color="#4a90a4" style={iconStyle} />
              <input type="text" value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Your full name" style={inputStyle} />
            </div>
          </div>
        )}

        {/* Email */}
        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '13px', color: '#6b7a8d', marginBottom: '8px', display: 'block' }}>Email Address</label>
          <div style={{ position: 'relative' }}>
            <Mail size={16} color="#4a90a4" style={iconStyle} />
            <input type="email" value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com" style={inputStyle} />
          </div>
        </div>

        {/* Password */}
        <div style={{ marginBottom: !isLogin ? '16px' : '8px' }}>
          <label style={{ fontSize: '13px', color: '#6b7a8d', marginBottom: '8px', display: 'block' }}>Password</label>
          <div style={{ position: 'relative' }}>
            <Lock size={16} color="#4a90a4" style={iconStyle} />
            <input type={showPass ? 'text' : 'password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              style={{ ...inputStyle, paddingRight: '42px' }} />
            <button onClick={() => setShowPass(!showPass)} style={{
              position: 'absolute', right: '14px', top: '50%',
              transform: 'translateY(-50%)', background: 'none',
              border: 'none', cursor: 'pointer', color: '#4a90a4'
            }}>
              {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        {/* Forgot Password */}
        {isLogin && (
          <div style={{ textAlign: 'right', marginBottom: '24px' }}>
            <span style={{ color: '#00d4ff', fontSize: '12px', cursor: 'pointer' }}>
              Forgot password?
            </span>
          </div>
        )}

        {/* Confirm Password (Register only) */}
        {!isLogin && (
          <div style={{ marginBottom: '24px' }}>
            <label style={{ fontSize: '13px', color: '#6b7a8d', marginBottom: '8px', display: 'block' }}>Confirm Password</label>
            <div style={{ position: 'relative' }}>
              <Lock size={16} color="#4a90a4" style={iconStyle} />
              <input type={showConfirmPass ? 'text' : 'password'}
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                style={{ ...inputStyle, paddingRight: '42px' }} />
              <button onClick={() => setShowConfirmPass(!showConfirmPass)} style={{
                position: 'absolute', right: '14px', top: '50%',
                transform: 'translateY(-50%)', background: 'none',
                border: 'none', cursor: 'pointer', color: '#4a90a4'
              }}>
                {showConfirmPass ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
        )}

        {/* Submit */}
        <button onClick={isLogin ? handleLogin : handleRegister}
          disabled={loading} style={{
            width: '100%', padding: '14px',
            background: loading ? '#1e2d3d' : 'linear-gradient(135deg, #00d4ff, #0066ff)',
            border: 'none', borderRadius: '10px',
            color: '#fff', fontSize: '15px', fontWeight: '600',
            cursor: loading ? 'not-allowed' : 'pointer',
            marginBottom: '20px',
            boxShadow: loading ? 'none' : '0 4px 20px rgba(0,212,255,0.3)',
          }}>
          {loading ? '⏳ Please wait...' : isLogin ? 'Sign In' : 'Create Account'}
        </button>

        {/* Divider */}
        <div style={{ textAlign: 'center', color: '#6b7a8d', fontSize: '13px', marginBottom: '20px' }}>
          or continue with
        </div>

        {/* Google */}
        <button onClick={handleGoogleLogin} style={{
          width: '100%', padding: '12px',
          background: 'transparent', border: '1px solid #1e2d3d',
          borderRadius: '10px', color: '#e1e4e8',
          fontSize: '14px', fontWeight: '500', cursor: 'pointer',
          display: 'flex', alignItems: 'center',
          justifyContent: 'center', gap: '10px'
        }}>
          <img src="https://www.google.com/favicon.ico" width="16" height="16" alt="Google" />
          Continue with Google
        </button>
      </div>
    </div>
  )
}