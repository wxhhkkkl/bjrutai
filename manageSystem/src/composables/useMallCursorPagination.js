import { ref } from 'vue'

export function useMallCursorPagination() {
  const currentPage = ref(1)
  const pageCursors = ref([null])

  function resetPages() {
    currentPage.value = 1
    pageCursors.value = [null]
  }

  function cursorForPage(page) {
    return pageCursors.value[page - 1] ?? null
  }

  function recordCursor(page, result) {
    const nextCursor = result?.nextCursor || null
    const nextCursors = pageCursors.value.slice(0, page)
    if (nextCursor) nextCursors[page] = nextCursor
    pageCursors.value = nextCursors
  }

  function recordPage(page, result) {
    recordCursor(page, result)
    currentPage.value = page
  }

  async function loadPage(page, fetchPage) {
    if (!Number.isInteger(page) || page < 1 || page === currentPage.value) {
      return null
    }

    if (page < currentPage.value) {
      const result = await fetchPage(cursorForPage(page))
      recordCursor(page, result)
      currentPage.value = page
      return result
    }

    let result = null
    for (let target = currentPage.value + 1; target <= page; target += 1) {
      const cursor = cursorForPage(target)
      if (target > 1 && !cursor) return null

      result = await fetchPage(cursor)
      recordCursor(target, result)
      if (target < page && !result?.nextCursor) return null
    }
    currentPage.value = page
    return result
  }

  return { currentPage, cursorForPage, loadPage, recordPage, resetPages }
}
