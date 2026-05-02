export interface UploadedImage {
  base64: string
  width: number
  height: number
  size_bytes: number
  format: string
}

export async function getImageFromClipboard(): Promise<UploadedImage | null> {
  if (!navigator.clipboard || !navigator.clipboard.read) {
    return null
  }

  try {
    const items = await navigator.clipboard.read()
    for (const item of items) {
      const imageTypes = item.types.filter((t) => t.startsWith('image/'))
      if (imageTypes.length === 0) continue

      for (const imageType of imageTypes) {
        const blob = await item.getType(imageType)
        if (blob.size === 0) continue

        if (blob.size > 5 * 1024 * 1024) {
          throw new Error(`Image too large: ${blob.size} bytes exceeds 5MB limit`)
        }

        const formData = new FormData()
        const ext = imageType.split('/')[1] || 'png'
        formData.append('file', blob, `clipboard.${ext}`)

        const response = await fetch('/api/v1/upload/image', {
          method: 'POST',
          body: formData,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.message || `Upload failed with status ${response.status}`)
        }

        const result: UploadedImage = await response.json()
        return result
      }
    }
    return null
  } catch (e) {
    if (e instanceof DOMException && e.name === 'NotAllowedError') {
      console.warn('Clipboard read permission denied')
      return null
    }
    throw e
  }
}
