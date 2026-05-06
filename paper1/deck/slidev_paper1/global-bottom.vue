<script setup lang="ts">
import { useNav } from '@slidev/client'

const { currentPage, total } = useNav()
</script>

<template>
  <footer
    class="pointer-events-none absolute bottom-0 left-0 right-0 z-30 flex justify-end px-6 pb-3 pt-1 text-sm text-slate-500 tabular-nums dark:text-slate-400"
  >
    <span>{{ currentPage }} / {{ total }}</span>
  </footer>
</template>
