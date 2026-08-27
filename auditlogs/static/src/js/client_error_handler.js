/** @odoo-module **/

import { registry } from "@web/core/registry";

const clientErrorHandlerService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        const STORAGE_KEY = "auditlog_pending_client_errors";

        const getDeviceType = () => {
            const ua = navigator.userAgent;
            if (/(tablet|ipad|playbook|silk)|(android(?!.*mobi))/i.test(ua)) {
                return "Tablet";
            }
            if (
                /Mobile|iP(hone|od)|Android|BlackBerry|IEMobile|Kindle|Silk-Accelerated|(hpw|web)OS|Opera M(obi|ini)/.test(
                    ua
                )
            ) {
                return "Telefono";
            }
            return "Computadora";
        };

        const getFriendlyErrorName = (message, stack) => {
            const textToCheck = ((message || "") + " " + (stack || "")).toLowerCase();
            
            if (
                textToCheck.includes("connectionlosterror") ||
                (textToCheck.includes("connection to") && textToCheck.includes("couldn't be established")) ||
                textToCheck.includes("err_connection_timed_out") ||
                textToCheck.includes("err_internet_disconnected") ||
                textToCheck.includes("err_network_changed") ||
                textToCheck.includes("networkerror") ||
                textToCheck.includes("failed to fetch") ||
                textToCheck.includes("an error occured in the owl lifecycle")
            ) {
                return "Fallo de Conexión";
            }
            return message || "Unknown Error";
        };

        const saveError = (errorData) => {
            try {
                const pending = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
                pending.push(errorData);
                localStorage.setItem(STORAGE_KEY, JSON.stringify(pending));
                trySendErrors();
            } catch (e) {
                console.error("Auditlog: Failed to save error to localStorage", e);
            }
        };

        const trySendErrors = async () => {
            const pending = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
            if (pending.length === 0) return;

            try {
                await orm.create("auditlog.client.error", pending);
                localStorage.removeItem(STORAGE_KEY);
            } catch (e) {
                // console.warn("Auditlog: Failed to send client errors", e);
            }
        };

        window.addEventListener("error", (event) => {
            const message = event.message || "Unknown Error";
            const stack = event.error ? event.error.stack : "";
            const errorData = {
                name: getFriendlyErrorName(message, stack),
                message: message,
                stack_trace: stack,
                url: window.location.href,
                user_agent: navigator.userAgent,
                device_type: getDeviceType(),
                client_timestamp: new Date().toISOString(),
            };
            saveError(errorData);
        });

        window.addEventListener("unhandledrejection", (event) => {
            let message = "Unhandled Rejection";
            let stack = "";
            let name = null;

            if (event.reason) {
                // Check for Odoo RPC Errors
                if (event.reason.data && event.reason.data.name) {
                    const errName = event.reason.data.name;
                    if (errName.endsWith("UserError")) {
                        name = "User Error";
                    } else if (errName.endsWith("ValidationError")) {
                        name = "Validation Error";
                    } else if (errName.endsWith("AccessDenied") || errName.endsWith("AccessError")) {
                        name = "Access Error";
                    } else {
                        name = errName;
                    }
                    message = event.reason.data.message;
                    stack = event.reason.data.debug || "";
                } else if (event.reason instanceof Error) {
                    message = event.reason.message;
                    stack = event.reason.stack || "";
                    if (event.reason.cause) {
                         const causeMsg = event.reason.cause.message || event.reason.cause.toString();
                         message += " | Caused by: " + causeMsg;
                         if (event.reason.cause.stack) {
                             stack += "\nCaused by: " + event.reason.cause.stack;
                         }
                    }
                } else {
                    message = event.reason.toString();
                }
            }
            const errorData = {
                name: name || getFriendlyErrorName(message, stack),
                message: message,
                stack_trace: stack,
                url: window.location.href,
                user_agent: navigator.userAgent,
                device_type: getDeviceType(),
                client_timestamp: new Date().toISOString(),
            };
            saveError(errorData);
        });

        trySendErrors();
        setInterval(trySendErrors, 60000);
    },
};

registry.category("services").add("auditlog_client_error_handler", clientErrorHandlerService);
