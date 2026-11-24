import { Component, type ReactNode } from "react";

export class OptionalBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed
      ? <p className="alert" role="alert">Synthetic tests could not be loaded.</p>
      : this.props.children;
  }
}
