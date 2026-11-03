import { createContext, useContext } from 'react'
export const DockContext = createContext(null)
export const useConversationDock = () => useContext(DockContext)
