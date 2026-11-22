import gsap from 'gsap'
import { useGSAP } from '@gsap/react'

gsap.registerPlugin(useGSAP)
gsap.config({ nullTargetWarn: false })

/** Animation runs only when neither the device nor the student's own setting asks for reduced motion. */
export function motionOK(): boolean {
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches && document.documentElement.dataset.motion !== 'reduce'
}

export { gsap, useGSAP }
