import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDebouncedCallback } from "@/hooks/useDebouncedCallback";

describe("useDebouncedCallback", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("ruft die Callback erst nach Ablauf der Verzögerung auf", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(callback, 800));

    act(() => result.current("a"));
    expect(callback).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(799));
    expect(callback).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(callback).toHaveBeenCalledExactlyOnceWith("a");
  });

  it("nur der letzte Aufruf innerhalb des Fensters feuert (Tippen ohne Pause)", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(callback, 800));

    act(() => result.current("a"));
    act(() => vi.advanceTimersByTime(400));
    act(() => result.current("ab"));
    act(() => vi.advanceTimersByTime(400));
    expect(callback).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(400));
    expect(callback).toHaveBeenCalledExactlyOnceWith("ab");
  });

  it("räumt den ausstehenden Timer beim Unmount auf", () => {
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useDebouncedCallback(callback, 800));

    act(() => result.current("a"));
    unmount();
    act(() => vi.advanceTimersByTime(800));

    expect(callback).not.toHaveBeenCalled();
  });

  it("flush() führt den ausstehenden Aufruf sofort aus", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(callback, 800));

    act(() => result.current("a"));
    act(() => result.current.flush());
    expect(callback).toHaveBeenCalledExactlyOnceWith("a");

    act(() => vi.advanceTimersByTime(800));
    expect(callback).toHaveBeenCalledOnce();
  });

  it("flush() ohne ausstehenden Aufruf tut nichts", () => {
    const callback = vi.fn();
    const { result } = renderHook(() => useDebouncedCallback(callback, 800));

    act(() => result.current.flush());
    expect(callback).not.toHaveBeenCalled();
  });

  it("flush() nach dem Unmount holt einen ausstehenden Aufruf nach", () => {
    const callback = vi.fn();
    const { result, unmount } = renderHook(() => useDebouncedCallback(callback, 800));

    act(() => result.current("a"));
    const { flush } = result.current;
    unmount();
    flush();

    expect(callback).toHaveBeenCalledExactlyOnceWith("a");
  });
});
