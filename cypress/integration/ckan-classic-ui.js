const cypressUpload = require('cypress-file-upload')

Cypress.on('uncaught:exception', (err, runnable) => {
  console.log(err);
  return false;
})

describe('CKAN Classic UI', () => {
  beforeEach(function(){
    cy.clearCookies()
    cy.fixture('aircan.json').as('testData').then(() => {
      cy.login(this.testData.username, this.testData.password)
    })
  })

  it('Creating a new package from the UI', () => {
    cy.createDataset().then((datasetName) => {
      cy.location('pathname').should('eq', '/dataset/' + datasetName)
      cy.deleteDataset(datasetName)
    })
  })

  it('Adding a new resource from the UI', () => {
    cy.createDataset().then((datasetName) => {
      cy.get('.content_action > .btn').click()
      cy.get('.page-header > .nav > :nth-child(2) > a').click()
      cy.get('.page_primary_action > .btn').click()
      cy.get('#field-image-upload').attachFile({ filePath: 'sample2.csv', fileName: 'sample2.csv' })
      cy.get('#field-name').type('sample2')
      cy.get('.form-actions > .btn').click()
      cy.contains('sample2')
      cy.deleteDataset(datasetName)
    })
  })

  it('Uploads Excel file successfully and creates a preview (data explorer)', () => {
    cy.createDatasetWithoutFile().then((datasetName) => {
      cy.get('#field-image-upload').attachFile({ filePath: 'sample.xlsx', fileName: 'sample.xlsx' })
      cy.get('#field-name').type('sample xlsx')
      cy.get('#select2-chosen-1').type('XLSX{enter}')
      cy.get('.btn-primary').click()
      cy.get('.resource-item > .heading').click()
      cy.get('.module-content > .nav > .active > a').contains('Data Explorer')
      cy.deleteDataset(datasetName)
    })
  })

  it('Upload PDF and check its preview', () => {
    cy.createDatasetWithoutFile().then((datasetName) => {
      cy.get('#field-image-upload').attachFile({ filePath: 'sample-pdf-with-images.pdf', fileName: 'sample-pdf-with-images.pdf' })
      cy.get('.btn-primary').click()
      cy.location('pathname').should('eq', '/dataset/' + datasetName)
      cy.get('.resource-item > .heading').click()
      // Check if PDF preview exists
      cy.get('.module-content > .nav > .active > a').contains('PDF')
      cy.get('iframe').should('exist')
      cy.deleteDataset(datasetName)
    })
  })

  it('Upload large PDF and check its preview', () => {
    cy.createDatasetWithoutFile().then((datasetName) => {
      cy.get('#field-image-upload').attachFile({ filePath: 'sample-pdf-large-size.pdf', fileName: 'sample-pdf-large-size.pdf' })
      cy.get('.btn-primary').click()
      cy.location('pathname').should('eq', '/dataset/' + datasetName)
      // Check if PDF preview exists
      cy.get('.resource-item > .heading').click()
      cy.get('.module-content > .nav > .active > a').contains('PDF')
      cy.get('iframe').should('exist')
      cy.deleteDataset(datasetName)
    })
  })

  it('Adding a new organization from the UI', () => {
    cy.createOrganization().then((orgName) => {
      cy.deleteOrganization(orgName)
    })
  })

  it('Make a dataset subscribable and then unsubscribable', () => {
    cy.createDataset().then((datasetName) => {
      cy.location('pathname').should('eq', '/dataset/' + datasetName)
      cy.get('.content_action > .btn').click()
      cy.get('.select2-choices').type('subscribable{enter}')
      cy.get('.btn-primary').click()
      cy.get('.tag-list').contains('subscribable')
      // Now make it unsubscribable
      // cy.visit('/dataset/' + datasetName)
      // cy.get('.content_action > .btn').click()
      // cy.get('.select2-search-choice > .select2-search-choice-close').click()
      // cy.get('.btn-primary').click()

      cy.deleteDataset(datasetName)
    })
  })

})
