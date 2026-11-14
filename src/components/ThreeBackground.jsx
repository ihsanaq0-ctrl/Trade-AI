import { useEffect, useRef } from 'react'
import * as THREE from 'three'

/**
 * ThreeBackground — animated 3D scene used as a full-screen backdrop.
 *
 * Elements:
 *  - Floating 3D candlestick pillars (green/red) gently bobbing
 *  - Particle starfield
 *  - Two rotating wireframe rings
 *
 * Theme-matched to the app: bg #0a0e17, cyan #00d4ff, blue #0066ff,
 * green #00ff88, red #ff4757.
 *
 * Props:
 *  - density: number of floating pillars (default 40)
 *  - opacity: canvas CSS opacity (default 0.55)
 */
export default function ThreeBackground({ density = 40, opacity = 0.55 }) {
  const mountRef = useRef(null)

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    // ---- Scene / camera / renderer ----
    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x0a0e17, 0.004)

    const camera = new THREE.PerspectiveCamera(
      60,
      mount.clientWidth / Math.max(mount.clientHeight, 1),
      0.1,
      1000
    )
    camera.position.set(0, 5, 24)
    camera.lookAt(0, 0, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(mount.clientWidth, mount.clientHeight)
    mount.appendChild(renderer.domElement)

    const group = new THREE.Group()
    scene.add(group)

    // ---- Floating candlestick pillars ----
    const bodyGeo = new THREE.BoxGeometry(0.55, 1, 0.55)
    const wickGeo = new THREE.CylinderGeometry(0.045, 0.045, 1.7, 6)
    const matUp = new THREE.MeshStandardMaterial({
      color: 0x00ff88, transparent: true, opacity: 0.6,
      emissive: 0x00ff88, emissiveIntensity: 0.18,
    })
    const matDown = new THREE.MeshStandardMaterial({
      color: 0xff4757, transparent: true, opacity: 0.6,
      emissive: 0xff4757, emissiveIntensity: 0.18,
    })
    const matNeutral = new THREE.MeshStandardMaterial({
      color: 0x00d4ff, transparent: true, opacity: 0.45,
      emissive: 0x00d4ff, emissiveIntensity: 0.12,
    })

    const pillars = []
    const count = Math.max(10, density)
    for (let i = 0; i < count; i++) {
      const roll = Math.random()
      const mat = roll < 0.4 ? matUp : roll < 0.8 ? matDown : matNeutral
      const body = new THREE.Mesh(bodyGeo, mat)
      const h = 0.8 + Math.random() * 1.8
      body.scale.y = h
      body.position.set(
        (Math.random() - 0.5) * 36,
        (Math.random() - 0.5) * 7,
        (Math.random() - 0.5) * 22 - 5
      )
      body.rotation.y = Math.random() * Math.PI

      const wick = new THREE.Mesh(wickGeo, mat)
      wick.position.copy(body.position)
      wick.position.y += (h * 0.5) * 0.5 + 0.75

      group.add(body, wick)
      pillars.push({
        body, wick,
        speed: 0.2 + Math.random() * 0.7,
        phase: Math.random() * Math.PI * 2,
        bobAmp: 0.003 + Math.random() * 0.005,
      })
    }

    // ---- Particle starfield ----
    const starCount = 500
    const starGeo = new THREE.BufferGeometry()
    const starPos = new Float32Array(starCount * 3)
    for (let i = 0; i < starCount * 3; i += 3) {
      starPos[i] = (Math.random() - 0.5) * 70
      starPos[i + 1] = (Math.random() - 0.5) * 32
      starPos[i + 2] = (Math.random() - 0.5) * 45 - 6
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3))
    const starMat = new THREE.PointsMaterial({
      color: 0x00d4ff, size: 0.13, transparent: true, opacity: 0.65,
    })
    const stars = new THREE.Points(starGeo, starMat)
    group.add(stars)

    // ---- Wireframe rings ----
    const ringGeo = new THREE.TorusGeometry(9.5, 0.06, 8, 80)
    const ringMatA = new THREE.MeshBasicMaterial({
      color: 0x0066ff, transparent: true, opacity: 0.22, wireframe: true,
    })
    const ringMatB = new THREE.MeshBasicMaterial({
      color: 0x00d4ff, transparent: true, opacity: 0.14, wireframe: true,
    })
    const ringA = new THREE.Mesh(ringGeo, ringMatA)
    ringA.rotation.x = Math.PI / 2.4
    const ringB = new THREE.Mesh(ringGeo, ringMatB)
    ringB.scale.set(0.68, 0.68, 0.68)
    ringB.rotation.x = Math.PI / 1.75
    group.add(ringA, ringB)

    // ---- Lights ----
    scene.add(new THREE.AmbientLight(0xffffff, 0.4))
    const dir = new THREE.DirectionalLight(0xffffff, 0.7)
    dir.position.set(6, 12, 8)
    scene.add(dir)
    const dir2 = new THREE.DirectionalLight(0x00d4ff, 0.35)
    dir2.position.set(-8, -4, -6)
    scene.add(dir2)

    // ---- Animation loop ----
    let raf = 0
    const clock = new THREE.Clock()
    const animate = () => {
      raf = requestAnimationFrame(animate)
      const t = clock.getElapsedTime()
      for (const p of pillars) {
        p.body.position.y += Math.sin(t * p.speed + p.phase) * p.bobAmp
        p.wick.position.y = p.body.position.y + (p.body.scale.y * 0.5) * 0.5 + 0.75
        p.body.rotation.y += 0.0018
      }
      stars.rotation.y += 0.00035
      ringA.rotation.z += 0.0011
      ringB.rotation.z -= 0.0016
      if (!reducedMotion) {
        group.rotation.y = Math.sin(t * 0.05) * 0.28
      }
      renderer.render(scene, camera)
    }
    animate()

    // ---- Resize ----
    const onResize = () => {
      const w = mount.clientWidth
      const h = Math.max(mount.clientHeight, 1)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    const onContextLost = (e) => e.preventDefault()
    renderer.domElement.addEventListener('webglcontextlost', onContextLost)

    // ---- Cleanup ----
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      renderer.domElement.removeEventListener('webglcontextlost', onContextLost)
      group.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose()
        if (obj.material) {
          if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose())
          else obj.material.dispose()
        }
      })
      starGeo.dispose()
      ringGeo.dispose()
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement)
      }
    }
  }, [density])

  return (
    <div
      ref={mountRef}
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        opacity,
        pointerEvents: 'none',
      }}
    />
  )
}
