import type { NavOperations, ShortcutOptions } from '@slidev/types'

/**
 * ↓/↑ 默认绑定整页跳转且开启 autoRepeat，长按会快速跳过大量页面并跳过 v-click。
 * 改为与 →/← 一致的逐步前进/后退，并关闭长按连发。
 */
export default function (ctx: NavOperations, shortcuts: ShortcutOptions[]) {
  return shortcuts.map((s) => {
    if (s.name === 'next_down')
      return { ...s, fn: ctx.next, autoRepeat: false }
    if (s.name === 'prev_up')
      return { ...s, fn: ctx.prev, autoRepeat: false }
    return s
  })
}
