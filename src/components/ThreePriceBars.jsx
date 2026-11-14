import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

/**
 * ThreePriceBars — interactive 3D visualization of live market prices.
 *
 * Each instrument becomes a 3D pillar; height is normalized to the price
 * range, color reflects short-term direction (green = up, red = down).
 * Drag to orbit, scroll to zoom. Auto-rotates slowly.
 *
 * Props:
 *  - prices: [{ symbol, bid, ask, spread }]
 *  - height: canvas CSS height (default 300)
 *  - maxBars: max pillars to render (default 12)
 */
export default function ThreePriceBars({ prices = [], height = 300, maxBars = 12 }) {
  const mountRef = useRef(null)
  const sceneRef = useRef(null)

  // ---- One-time scene setup ----
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0d1117)

    const camera = new THREE.PerspectiveCamera(
      50,
      mount.clientWidth / Math.max(mount.clientHeight, 1),
      0.1,
      100
    )
    camera.position.set(0, 7, 14)
    camera.lookAt(0, 1.5, 0)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(mount.clientWidth, mount.clientHeight)
    mount.appendChild(renderer.domElement)

    // Lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.55))
    const dir = new THREE.DirectionalLight(0xffffff, 0.85)
    dir.position.set(6, 12, 8)
    scene.add(dir)
    const fill = new THREE.DirectionalLight(0x00d4ff, 0.3)
    fill.position.set(-6, 2, -4)
    scene.add(fill)

    // Ground grid
    const grid = new THREE.GridHelper(26, 13, 0x1e2d3d, 0x1e2d3d)
    grid.position.y = 0
    scene.add(grid)

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.maxPolarAngle = Math.PI / 2.1
    controls.minDistance = 5
    controls.maxDistance = 30
    controls.autoRotate = !reducedMotion
    controls.autoRotateSpeed = 1.2
    controls.target.set(0, 1.5, 0)

    // Bars container
    const group = new THREE.Group()
    scene.add(group)

    // Animation loop
    let raf = 0
    const clock = new THREE.Clock()
    const animate = () => {
      raf = requestAnimationFrame(animate)
      const dt = clock.getDelta()
      controls.update(dt)
      renderer.render(scene, camera)
    }
    animate()

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

    sceneRef.current = {
      scene, camera, renderer, controls, group, mount, clock,
    }

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      renderer.domElement.removeEventListener('webglcontextlost', onContextLost)
      scene.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose()
        if (obj.material) {
          if (Array.isArray(obj.material)) obj.material.forEach((m) => m.dispose())
          else obj.material.dispose()
        }
      })
      controls.dispose()
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) {
        mount.removeChild(renderer.domElement)
      }
      sceneRef.current = null
    }
  }, [])

  // ---- Update bars when prices change ----
  useEffect(() => {
    const s = sceneRef.current
    if (!s) return

    const { group } = s
    // Remove old bars
    while (group.children.length) {
      const child = group.children[0]
      group.remove(child)
      if (child.geometry) child.geometry.dispose()
      if (child.material) {
        if (Array.isArray(child.material)) child.material.forEach((m) => m.dispose())
        else child.material.dispose()
      }
    }

    const data = (prices || []).slice(0, maxBars)
    if (data.length === 0) return

    const bids = data.map((p) => p.bid).filter((v) => typeof v === 'number')
    if (bids.length === 0) return

    const min = Math.min(...bids)
    const max = Math.max(...bids)
    const range = max - min || 1

    const barGeo = new THREE.BoxGeometry(1, 1, 1)
    const spacer = 1.9
    const offset = ((data.length - 1) * spacer) / 2

    const matUp = new THREE.MeshStandardMaterial({
      color: 0x00ff88, emissive: 0x00ff88, emissiveIntensity: 0.25,
    })
    const matDown = new THREE.MeshStandardMaterial({
      color: 0xff4757, emissive: 0xff4757, emissiveIntensity: 0.25,
    })

    data.forEach((p, i) => {
      const h = 0.6 + ((p.bid - min) / range) * 6.5
      const prevBid = data[i - 1]?.bid
      const up = prevBid === undefined ? true : p.bid >= prevBid
      const bar = new THREE.Mesh(barGeo, up ? matUp : matDown)
      bar.scale.set(1.15, h, 1.15)
      bar.position.set(i * spacer - offset, h / 2, 0)
      group.add(bar)
    })

    // Dispose shared geometries/materials after loop
    barGeo.dispose()
    matUp.dispose()
    matDown.dispose()
  }, [prices, maxBars])

  return (
    <div
      ref={mountRef}
      style={{
        width: '100%',
        height,
        borderRadius: '12px',
        overflow: 'hidden',
        background: '#0d1117',
        border: '1px solid #1e2d3d',
        cursor: 'grab',
        position: 'relative',
      }}
    />
  )
}
