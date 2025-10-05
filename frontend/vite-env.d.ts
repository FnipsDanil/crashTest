/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_HMAC_SECRET_KEY: string
  readonly VITE_DEV_PORT: string
  readonly VITE_GIFT_BOT_USERNAME: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// Override NodeJS.Timeout to be number in browser environment
declare namespace NodeJS {
  type Timeout = number;
}

declare module 'react-dom/client' {
  import { Container } from 'react-dom';
  
  export interface Root {
    render(children: React.ReactNode): void;
    unmount(): void;
  }
  
  export function createRoot(container: Element | DocumentFragment): Root;
  export function hydrateRoot(container: Element | Document, initialChildren: React.ReactNode): Root;
}