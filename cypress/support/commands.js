// ***********************************************
// This example commands.js shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************
//
//
// -- This is a parent command --
// Cypress.Commands.add("login", (email, password) => { ... })
//
//
// -- This is a child command --
// Cypress.Commands.add("drag", { prevSubject: 'element'}, (subject, options) => { ... })
//
//
// -- This is a dual command --
// Cypress.Commands.add("dismiss", { prevSubject: 'optional'}, (subject, options) => { ... })
//
//
// -- This will overwrite an existing command --
// Cypress.Commands.overwrite("visit", (originalFn, url, options) => { ... })

const cypressUpload = require('cypress-file-upload')

const getRandomDatasetName = () => Math.random().toString(36).slice(2) + '_dataset_test'
const getRandomOrganizationName = () => Math.random().toString(36).slice(2) + '_organization_test'

Cypress.Commands.add('login', (email, password) => {
    cy.visit({url: '/user/_logout'}).then(() => {
      cy.visit({url: '/user/login'}).then((resp) => {
        cy.get('#field-login').type(email)
        cy.get('#field-password').type(password)
        cy.get('#field-remember').check()
        cy.get('.form-actions > .btn').click({force: true})
      })
    })
});


Cypress.Commands.add('createDatasetWithoutFile', (name) => {
  cy.visit({url: '/dataset'}).then((resp) => {
    const datasetName = name || getRandomDatasetName()
    cy.get('.page_primary_action > .btn').click()
    cy.get('#field-title').type(datasetName)
    cy.get('.btn-xs').click()
    cy.get('#field-name').clear().type(datasetName)
    cy.get('button.btn-primary[type=submit]').click()
    cy.wrap(datasetName)
  })
})

Cypress.Commands.add('createDataset', () => {
  cy.visit({url: '/dataset'}).then((resp) => {
    const datasetName = getRandomDatasetName()
    cy.get('.page_primary_action > .btn').click()
    cy.get('#field-title').type(datasetName)
    cy.get('.btn-xs').click()
    cy.get('#field-name').clear().type(datasetName)
    cy.get('button.btn-primary[type=submit]').click()
    cy.get('#field-image-upload').attachFile({ filePath: 'sample.csv', fileName: 'sample.csv' })
    cy.get('.btn-primary').click()
    cy.get('.content_action > .btn')
    cy.wrap(datasetName)
  })
})

Cypress.Commands.add('createLinkedDataset', () => {
  cy.visit({url: '/dataset'}).then((resp) => {
    const datasetName = getRandomDatasetName()
    cy.get('.page_primary_action > .btn').click()
    cy.get('#field-title').type(datasetName)
    cy.get('.btn-xs').click()
    cy.get('#field-name').clear().type(datasetName)
    cy.get('button.btn-primary[type=submit]').click()
    cy.get('[title="Link to a URL on the internet (you can also link to an API)"]').click()
    cy.get('#field-image-url').clear().type('https://raw.githubusercontent.com/datapackage-examples/sample-csv/master/sample.csv')
    cy.get('.btn-primary').click()
    cy.get('.content_action > .btn')
    cy.wrap(datasetName)
  })
})

Cypress.Commands.add('deleteDataset', (datasetName) => {
  cy.visit({url: '/dataset/delete/' + datasetName}).then(() => {
    cy.get('form#confirm-dataset-delete-form > .btn-primary').click()
    cy.contains('Dataset has been deleted.')
  })
})


Cypress.Commands.add('createOrganization', () => {
  const organizationName = getRandomOrganizationName()
  cy.get('.nav > :nth-child(2) > a').first().click()
  cy.get('.page_primary_action > .btn').click()
  cy.get('#field-name').type(organizationName)
  cy.get('.btn-xs').click()
  cy.get('#field-url').clear().type(organizationName)
  cy.get('.form-actions > .btn').click()
  cy.location('pathname').should('eq', '/organization/' + organizationName)
  cy.wrap(organizationName)
})

Cypress.Commands.add('deleteOrganization', (orgName) => {
  cy.visit({url: '/organization/' + orgName}).then(() => {
    cy.get('.content_action > .btn').click()
    cy.get('.form-actions > .btn-danger').click()
    cy.get('.btn-primary').click()
    cy.contains('Organization has been deleted.')
  })
})
