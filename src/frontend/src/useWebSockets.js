import { useState, useRef, useEffect, useCallback } from "react";
export function useWebSocket(url) {
    const wsRef = useRef(null);
    const [connected, setConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState(null);
    const listenersRef = useRef([]);
   
    useEffect(() => {
      if (!url) return;
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;
   
        ws.onopen = () => setConnected(true);
        ws.onclose = () => setConnected(false);
        ws.onerror = () => setConnected(false);
        ws.onmessage = (evt) => {
          const data = JSON.parse(evt.data);
          setLastMessage(data);
          listenersRef.current.forEach((fn) => fn(data));
        };
   
        return () => ws.close();
      } catch {
        setConnected(false);
      }
    }, [url]);
   
    const send = useCallback((payload) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(payload));
      }
    }, []);
   
    const onMessage = useCallback((fn) => {
      listenersRef.current.push(fn);
      return () => {
        listenersRef.current = listenersRef.current.filter((f) => f !== fn);
      };
    }, []);
   
    return { connected, send, onMessage, lastMessage };
  }