import { useState, useRef, useEffect, useCallback } from "react";

const HEARTBEAT_INTERVAL = 35000; // ms — if no message received for 35s, we reconnect
const MAX_RECONNECT_DELAY = 60000; // ms

export function useWebSocket(url) {
    const wsRef = useRef(null);
    const [connected, setConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState(null);
    const listenersRef = useRef([]);
    const reconnectTimer = useRef(null);
    const heartbeatTimer = useRef(null);
    const lastMsgTimeRef = useRef(Date.now());
    const reconnectDelayRef = useRef(1000);
    const reconnectAttemptsRef = useRef(0);
    const pendingMessagesRef = useRef([]);

    useEffect(() => {
        if (!url) return;

        const checkHeartbeat = () => {
            const elapsed = Date.now() - lastMsgTimeRef.current;
            if (elapsed > HEARTBEAT_INTERVAL && wsRef.current?.readyState === WebSocket.OPEN) {
                console.warn("[WS] No message received for", elapsed, "ms — closing to reconnect");
                wsRef.current.close(4001, "heartbeat timeout");
            }
        };

        const connect = () => {
            try {
                const ws = new WebSocket(url);
                wsRef.current = ws;

                ws.onopen = () => {
                    console.log("[WS] Connected to", url);
                    setConnected(true);
                    reconnectAttemptsRef.current = 0;
                    reconnectDelayRef.current = 1000;
                    if (reconnectTimer.current) {
                        clearTimeout(reconnectTimer.current);
                        reconnectTimer.current = null;
                    }
                    lastMsgTimeRef.current = Date.now();
                    if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
                    heartbeatTimer.current = setInterval(checkHeartbeat, 5000);
                    // Flush pending messages
                    while (pendingMessagesRef.current.length > 0 && ws.readyState === WebSocket.OPEN) {
                        const p = pendingMessagesRef.current.shift();
                        ws.send(JSON.stringify(p));
                        console.log("[WS] Flushed pending", p.type);
                    }
                };

                ws.onclose = (e) => {
                    console.log("[WS] Disconnected", e.code, e.reason);
                    setConnected(false);
                    wsRef.current = null;
                    if (heartbeatTimer.current) {
                        clearInterval(heartbeatTimer.current);
                        heartbeatTimer.current = null;
                    }
                    // Exponential backoff
                    const delay = Math.min(
                        reconnectDelayRef.current * 2,
                        MAX_RECONNECT_DELAY
                    );
                    reconnectDelayRef.current = delay;
                    reconnectAttemptsRef.current += 1;
                    console.log(`[WS] Reconnecting in ${delay}ms (attempt #${reconnectAttemptsRef.current})`);
                    reconnectTimer.current = setTimeout(connect, delay);
                };

                ws.onerror = (e) => {
                    console.log("[WS] Error", e);
                    setConnected(false);
                    ws.close();
                };

                ws.onmessage = (evt) => {
                    lastMsgTimeRef.current = Date.now();
                    try {
                        const data = JSON.parse(evt.data);
                        // Ignore pure pings on the display side
                        if (data.type === "ping") {
                            // Optional pong echo
                            if (ws.readyState === WebSocket.OPEN) {
                                ws.send(JSON.stringify({ type: "pong", timestamp: data.timestamp }));
                            }
                            return;
                        }
                        console.log("[WS] Received", data.type, data);
                        setLastMessage(data);
                        listenersRef.current.forEach((fn) => fn(data));
                    } catch (e) {
                        console.error("WS parse error", e);
                    }
                };
            } catch {
                setConnected(false);
                const delay = Math.min(reconnectDelayRef.current * 2, MAX_RECONNECT_DELAY);
                reconnectDelayRef.current = delay;
                reconnectTimer.current = setTimeout(connect, delay);
            }
        };

        connect();

        return () => {
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
            if (heartbeatTimer.current) clearInterval(heartbeatTimer.current);
            if (wsRef.current) {
                wsRef.current.onclose = null; // prevent reconnection on unmount
                wsRef.current.close();
            }
        };
    }, [url]);

    const send = useCallback((payload) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            console.log("[WS] Sending", payload.type);
            wsRef.current.send(JSON.stringify(payload));
        } else {
            pendingMessagesRef.current.push(payload);
            console.warn("[WS] Not connected, queued", payload.type, "(queue:", pendingMessagesRef.current.length, ")");
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
