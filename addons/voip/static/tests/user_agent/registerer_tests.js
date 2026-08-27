/* @odoo-module */

import { Registerer } from "@voip/core/registerer";
import { UserAgent } from "@voip/core/user_agent_service";

import { browser } from "@web/core/browser/browser";
import { patchWithCleanup } from "@web/../tests/helpers/utils";

function makeVoip() {
    return {
        env: {
            services: {
                "voip.user_agent": {
                    attemptReconnection() {},
                },
            },
        },
        isUnloading: false,
        resolveError() {},
        triggerError() {},
    };
}

QUnit.module("voip registerer");

QUnit.test("register recreates SIP.js registerer stuck waiting", async (assert) => {
    const sipRegisterers = [];
    const addEventListener = window.addEventListener.bind(window);

    class FakeEventEmitter {
        constructor(assert, ownerIndex) {
            this.assert = assert;
            this.listeners = new Set();
            this.ownerIndex = ownerIndex;
        }

        addListener(listener) {
            this.listeners.add(listener);
        }

        removeListener(listener) {
            this.assert.step(`remove listener ${this.ownerIndex}`);
            this.listeners.delete(listener);
        }
    }

    patchWithCleanup(window, {
        addEventListener(type, listener, options) {
            if (type === "beforeunload") {
                return;
            }
            return addEventListener(type, listener, options);
        },
        SIP: {
            Registerer: class {
                constructor(userAgent, options) {
                    this.index = sipRegisterers.length;
                    this.options = options;
                    this.stateChange = new FakeEventEmitter(assert, this.index);
                    this.waiting = this.index === 0;
                    sipRegisterers.push(this);
                }

                dispose() {
                    assert.step(`dispose ${this.index}`);
                    this.disposed = true;
                    return Promise.resolve();
                }

                register() {
                    assert.step(`register ${this.index}`);
                    return Promise.resolve(`registered ${this.index}`);
                }

                unregister() {}
            },
        },
    });

    const registerer = new Registerer(makeVoip(), {});
    const registerPromise = registerer.register();

    assert.strictEqual(typeof registerPromise.then, "function");
    assert.strictEqual(sipRegisterers.length, 2);
    assert.ok(sipRegisterers[0].disposed);
    assert.strictEqual(sipRegisterers[0].stateChange.listeners.size, 0);
    assert.strictEqual(sipRegisterers[1].options.expires, Registerer.EXPIRATION_INTERVAL);
    assert.strictEqual(await registerPromise, "registered 1");
    assert.verifySteps(["remove listener 0", "dispose 0", "register 1"]);
});

QUnit.test("attemptReconnection schedules a retry when registration rejects", async (assert) => {
    let scheduledRetry;
    let scheduledDelay;

    patchWithCleanup(browser, {
        setTimeout(callback, delay) {
            scheduledRetry = callback;
            scheduledDelay = delay;
            return 1;
        },
    });

    const userAgent = Object.assign(Object.create(UserAgent.prototype), {
        __sipJsUserAgent: {
            reconnect() {
                assert.step("reconnect");
                return Promise.resolve();
            },
        },
        attemptingToReconnect: false,
        registerer: {
            register() {
                assert.step("register");
                return Promise.reject(new Error("REGISTER request already pending"));
            },
        },
        voip: {
            isUnloading: false,
            resolveError() {
                assert.step("resolve error");
            },
            triggerError() {},
        },
    });

    await userAgent.attemptReconnection(2);

    assert.notOk(userAgent.attemptingToReconnect);
    assert.ok(scheduledDelay >= 4000 && scheduledDelay < 4500);
    assert.strictEqual(typeof scheduledRetry, "function");

    userAgent.attemptReconnection = (attemptCount) => assert.step(`retry ${attemptCount}`);
    scheduledRetry();

    assert.verifySteps(["reconnect", "register", "retry 3"]);
});
