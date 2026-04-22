import './globals.css'
export const metadata = { title: 'APEE', description: 'Autonomous Personal Economy Engine' }
export default function RootLayout({ children }) {
  return <html lang="en"><body style={{height:'100vh',overflow:'hidden'}}>{children}</body></html>
}
