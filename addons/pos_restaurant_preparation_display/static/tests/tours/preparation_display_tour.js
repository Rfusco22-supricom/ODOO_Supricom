/** @odoo-module */
/* global posmodel */

import * as PaymentScreen from "@point_of_sale/../tests/tours/helpers/PaymentScreenTourMethods";
import * as ReceiptScreen from "@point_of_sale/../tests/tours/helpers/ReceiptScreenTourMethods";
import * as BillScreen from "@pos_restaurant/../tests/tours/helpers/BillScreenTourMethods";
import * as FloorScreen from "@pos_restaurant/../tests/tours/helpers/FloorScreenTourMethods";
import * as ProductScreenPos from "@point_of_sale/../tests/tours/helpers/ProductScreenTourMethods";
import * as ProductScreenResto from "@pos_restaurant/../tests/tours/helpers/ProductScreenTourMethods";
const ProductScreen = { ...ProductScreenPos, ...ProductScreenResto };
import { registry } from "@web/core/registry";

const waitUntilSynced = () => ({
    content: "Wait for the sendOrderInPreparationUpdateLastChange to be called and resolved",
    trigger: "body",
    run: async () => {
        const timout = 5000;
        const interval = 100;
        const attempts = timout / interval;
        for (let i = 0; i < attempts; i++) {
            if (posmodel.synch.pending == 0 && posmodel.synch.status == "connected") {
                await new Promise((r) => setTimeout(r, 200));
                return;
            }
            await new Promise((r) => setTimeout(r, interval));
        }
        throw new Error("Timeout waiting for sync");
    },
});

registry.category("web_tour.tours").add("PreparationDisplayTourResto", {
    test: true,
    url: "/pos/ui",
    steps: () =>
        [
            ProductScreen.confirmOpeningPopup(),

            // Create first order
            FloorScreen.clickTable("5"),
            ProductScreen.orderBtnIsPresent(),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.clickDisplayedProduct("Water"),
            ProductScreen.orderlineIsToOrder("Water"),
            ProductScreen.orderlineIsToOrder("Coca-Cola"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.isShown(),
            ReceiptScreen.clickNextOrder(),

            // Create second order
            FloorScreen.isShown(),
            FloorScreen.clickTable("4"),
            ProductScreen.orderBtnIsPresent(),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.orderlineIsToOrder("Coca-Cola"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.isShown(),
            ReceiptScreen.clickNextOrder(),

            // Create third order
            FloorScreen.isShown(),
            FloorScreen.clickTable("4"),
            ProductScreen.orderBtnIsPresent(),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.clickDisplayedProduct("Water"),
            ProductScreen.clickDisplayedProduct("Minute Maid"),
            ProductScreen.orderlineIsToOrder("Coca-Cola"),
            ProductScreen.orderlineIsToOrder("Water"),
            ProductScreen.orderlineIsToOrder("Minute Maid"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.selectedOrderlineHas("Minute Maid", "1.00"),
            ProductScreen.pressNumpad("⌫"),
            ProductScreen.selectedOrderlineHas("Minute Maid", "0.00"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.isShown(),
            ReceiptScreen.clickNextOrder(),
        ].flat(),
});

registry.category("web_tour.tours").add("PreparationDisplayTourInternalNotes", {
    test: true,
    url: "/pos/ui",
    steps: () =>
        [
            ProductScreen.confirmOpeningPopup(),
            FloorScreen.clickTable("5"),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.orderlineIsToOrder("Coca-Cola"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.addInternalNote("Test Internal Notes"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
        ].flat(),
});

registry.category("web_tour.tours").add("MakeBillTour", {
    test: true,
    steps: () =>
        [
            FloorScreen.clickTable("1"),
            ProductScreen.clickDisplayedProduct("Minute Maid"),
            ProductScreen.selectedOrderlineHas("Minute Maid", "1", "2.20"),
            BillScreen.clickBillButton(),
            BillScreen.isShown(),
            BillScreen.clickOk(),
        ].flat(),
});

registry.category("web_tour.tours").add("PreparationDisplayTourEmptyInternalNotes", {
    test: true,
    url: "/pos/ui",
    steps: () =>
        [
            ProductScreen.confirmOpeningPopup(),
            FloorScreen.clickTable("5"),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.orderlineIsToOrder("Coca-Cola"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.addInternalNote(""),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
        ].flat(),
});

registry.category("web_tour.tours").add("PreparationDisplayTourWithInternalNotes", {
    test: true,
    url: "/pos/ui",
    steps: () =>
        [
            ProductScreen.confirmOpeningPopup(),
            FloorScreen.clickTable("5"),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.orderlineIsToOrder("Coca-Cola"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.addInternalNote(""),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.clickDisplayedProduct("Coca-Cola"),
            ProductScreen.addInternalNote("Test Internal Notes"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
        ].flat(),
});

registry.category("web_tour.tours").add("PreparationDisplayChangeQuantityTour", {
    test: true,
    url: "/pos/ui",
    steps: () =>
        [
            ProductScreen.confirmOpeningPopup(),
            FloorScreen.clickTable("5"),
            ProductScreen.clickHomeCategory(),
            ProductScreen.orderBtnIsPresent(),
            ProductScreen.clickDisplayedProduct("Test Food"),
            ProductScreen.clickDisplayedProduct("Test Food"),
            ProductScreen.orderlineIsToOrder("Test Food"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.pressNumpad("Qty"),
            ProductScreen.pressNumpad("1"),
            ProductScreen.orderlineIsToOrder("Test Food"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
        ].flat(),
});

registry.category("web_tour.tours").add("test_update_internal_note_of_order", {
    test: true,
    steps: () =>
        [
            ProductScreen.confirmOpeningPopup(),
            FloorScreen.clickTable("5"),
            ProductScreen.clickHomeCategory(),
            ProductScreen.orderBtnIsPresent(),
            ProductScreen.clickDisplayedProduct("Test Food"),
            ProductScreen.orderlineIsToOrder("Test Food"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.addInternalNote("Test Internal Notes"),
            ProductScreen.selectedOrderlineHas("Test Food", "1.0"),
            ProductScreen.pressNumpad("⌫"),
            ProductScreen.selectedOrderlineHas("Test Food", "0.0"),
            ProductScreen.pressNumpad("⌫"),
            ProductScreen.orderIsEmpty(),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.clickDisplayedProduct("Demo Food"),
            ProductScreen.clickOrderButton(),
            waitUntilSynced(),
            ProductScreen.orderlinesHaveNoChange(),
            ProductScreen.totalAmountIs("10"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            waitUntilSynced(),
        ].flat(),
});
