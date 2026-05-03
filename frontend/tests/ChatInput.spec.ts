import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ChatInput from "../src/components/ChatInput.vue";

describe("ChatInput", () => {
  it("renders input textarea and send button", () => {
    const wrapper = mount(ChatInput, {
      props: { disabled: false },
    });

    const textarea = wrapper.find("textarea");
    expect(textarea.exists()).toBe(true);

    const button = wrapper.find("button");
    expect(button.exists()).toBe(true);
  });

  it("emits submit on Enter without shift", async () => {
    const wrapper = mount(ChatInput, {
      props: { disabled: false },
    });

    const textarea = wrapper.find("textarea");
    await textarea.setValue("test message");
    await textarea.trigger("keydown", { key: "Enter", shiftKey: false });

    expect(wrapper.emitted("submit")).toBeTruthy();
  });

  it("disables input when disabled prop is true", () => {
    const wrapper = mount(ChatInput, {
      props: { disabled: true },
    });

    const textarea = wrapper.find("textarea");
    expect(textarea.attributes("disabled")).toBeDefined();
  });

  it("renders in default state without crashing", () => {
    const wrapper = mount(ChatInput, {
      props: { disabled: false },
    });
    expect(wrapper.html()).toContain("textarea");
  });
});

